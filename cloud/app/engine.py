"""
Cloud engine — wraps MemChip's extraction pipeline and retrieval
with PostgreSQL multi-tenant storage and vector search.

v0.4.0: project registry, task management, agent auto-routing
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re as re_mod
import time
import uuid
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select, delete, update, text, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Memory, Relation, MemoryAudit, PoolAccess,
    MemoryInstruction, Webhook, MemorySession, MemorySchema,
    MemoryEvent, MemorySubscription,
    Project, Task, AgentContext,
)
from app.config import OPENROUTER_API_KEY, LLM_MODEL, EMBEDDING_MODEL, REDIS_URL

# Import MemChip extraction pipeline and LLM
import sys, os
sys.path.insert(0, "/app/memchip_core")
from memchip.extraction.pipeline import ExtractionPipeline
from memchip.retrieval.prompts import SUFFICIENCY_CHECK_PROMPT, MULTI_QUERY_PROMPT, ANSWER_PROMPT
from memchip.retrieval.engine import ENTITY_EXTRACTION_PROMPT
from memchip.llm import call_llm

# Lazy-loaded embedder
_embedder = None

# Decay constant: lambda = 0.001 (~30 day half-life)
DECAY_LAMBDA = 0.001


def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def embed_text(text: str) -> bytes:
    """Embed text and return as bytes."""
    model = get_embedder()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.astype(np.float32).tobytes()


def cosine_sim(a: bytes, b: bytes) -> float:
    """Cosine similarity between two embedding byte blobs."""
    va = np.frombuffer(a, dtype=np.float32)
    vb = np.frombuffer(b, dtype=np.float32)
    return float(np.dot(va, vb))


def get_extractor() -> ExtractionPipeline:
    return ExtractionPipeline(
        provider="openrouter",
        model=LLM_MODEL,
        api_key=OPENROUTER_API_KEY,
    )


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re_mod.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re_mod.sub(r'[\s_]+', '-', slug)
    slug = re_mod.sub(r'-+', '-', slug)
    return slug.strip('-')


# ========== Event Log ==========

async def create_memory_event(
    db: AsyncSession,
    org_id: str,
    memory_id: str,
    event_type: str,
    actor_id: Optional[str] = None,
    actor_type: str = "system",
    source: Optional[str] = None,
    previous_content: Optional[str] = None,
    new_content: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> MemoryEvent:
    """Create an immutable event log entry."""
    event = MemoryEvent(
        org_id=org_id,
        memory_id=memory_id,
        event_type=event_type,
        actor_id=actor_id,
        actor_type=actor_type,
        source=source,
        previous_content=previous_content,
        new_content=new_content,
        metadata_=metadata or {},
    )
    db.add(event)
    await db.flush()

    # Notify subscribers
    await notify_subscribers(db, org_id, event)

    return event


async def notify_subscribers(
    db: AsyncSession,
    org_id: str,
    event: MemoryEvent,
):
    """Check subscriptions and publish matching events to Redis."""
    stmt = select(MemorySubscription).where(
        MemorySubscription.org_id == org_id,
        MemorySubscription.is_active == True,
    )
    result = await db.execute(stmt)
    subs = result.scalars().all()

    if not subs:
        return

    # Load the memory to check scope/pool/categories
    mem_result = await db.execute(select(Memory).where(Memory.id == event.memory_id))
    mem = mem_result.scalar_one_or_none()

    matched_agents = set()
    for sub in subs:
        # Check event_type filter
        if sub.event_types and event.event_type not in sub.event_types:
            continue
        # Check scope filter
        if sub.scope_filter and mem and mem.scope != sub.scope_filter:
            continue
        # Check pool filter
        if sub.pool_filter and mem and mem.pool_id != sub.pool_filter:
            continue
        # Check category filter
        if sub.category_filter and mem:
            cats = mem.categories or []
            if sub.category_filter not in cats:
                continue
        matched_agents.add(sub.agent_id)

    if not matched_agents:
        return

    # Publish to Redis for each matched agent
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        payload = json.dumps({
            "event": f"memory.{event.event_type}",
            "memory_id": event.memory_id,
            "org_id": org_id,
            "actor_id": event.actor_id,
            "data": event.metadata_ or {},
        })
        for agent_id in matched_agents:
            await r.publish(f"memchip:memory:agent:{agent_id}", payload)
        await r.aclose()
    except Exception:
        pass  # Best effort


# ========== Audit Logging ==========

async def log_audit(
    db: AsyncSession,
    org_id: str,
    memory_id: str,
    action: str,
    actor_id: Optional[str] = None,
    actor_type: str = "system",
    details: Optional[Dict] = None,
):
    """Log an audit entry for a memory operation."""
    audit = MemoryAudit(
        org_id=org_id,
        memory_id=memory_id,
        action=action,
        actor_id=actor_id,
        actor_type=actor_type,
        details=details or {},
    )
    db.add(audit)


# ========== Access Control ==========

async def check_pool_access(
    db: AsyncSession,
    org_id: str,
    agent_id: str,
    pool_id: str,
    permission: str,
) -> bool:
    """Check if agent has a specific permission on a pool. Returns True if allowed.
    If no ACL entries exist for this pool at all, it's an open pool — allow access.
    Only enforce ACL when entries exist (i.e., pool has been explicitly secured)."""
    if not pool_id or not agent_id:
        return True  # No pool or no agent = no restriction
    # Check if ANY ACL entries exist for this pool
    any_acl_stmt = select(PoolAccess).where(
        PoolAccess.org_id == org_id,
        PoolAccess.pool_id == pool_id,
    ).limit(1)
    any_acl = (await db.execute(any_acl_stmt)).scalar_one_or_none()
    if not any_acl:
        return True  # No ACL entries for this pool = open access
    # ACL exists, check this agent's specific permissions
    stmt = select(PoolAccess).where(
        PoolAccess.org_id == org_id,
        PoolAccess.pool_id == pool_id,
        PoolAccess.agent_id == agent_id,
    )
    result = await db.execute(stmt)
    access = result.scalar_one_or_none()
    if not access:
        return False  # ACL exists but agent not listed = denied
    perms = access.permissions or {}
    return bool(perms.get(permission, False)) or bool(perms.get("admin", False))


# ========== Instructions ==========

async def get_active_instructions(
    db: AsyncSession,
    org_id: str,
    user_id: str,
) -> List[str]:
    """Fetch active memory instructions for a user."""
    stmt = select(MemoryInstruction).where(
        MemoryInstruction.org_id == org_id,
        MemoryInstruction.user_id == user_id,
        MemoryInstruction.is_active == True,
    )
    result = await db.execute(stmt)
    return [inst.instruction for inst in result.scalars().all()]


# ========== Webhook Firing ==========

async def fire_webhooks(
    db: AsyncSession,
    org_id: str,
    event: str,
    payload: Dict[str, Any],
):
    """Fire webhooks for an event asynchronously."""
    stmt = select(Webhook).where(
        Webhook.org_id == org_id,
        Webhook.is_active == True,
    )
    result = await db.execute(stmt)
    hooks = result.scalars().all()

    import httpx

    for hook in hooks:
        events = hook.events or []
        if event not in events:
            continue
        body = json.dumps({"event": event, "data": payload, "timestamp": datetime.utcnow().isoformat()})
        headers = {"Content-Type": "application/json"}
        if hook.secret:
            sig = hmac.new(hook.secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-MemChip-Signature"] = sig
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(hook.url, content=body, headers=headers)
        except Exception:
            pass  # Fire and forget


# ========== Deduplication (v0.3.0: conflict-aware) ==========

async def _find_duplicate(
    db: AsyncSession,
    org_id: str,
    user_id: str,
    content: str,
    embedding: bytes,
) -> tuple:
    """
    Check for duplicates. Returns (action, existing_memory_or_none, chain_id_or_none).
    action: "duplicate", "near_duplicate", or "new"

    v0.3.0: "duplicate" now means supersede (not merge).
    """
    stmt = select(Memory).where(
        Memory.org_id == org_id,
        Memory.user_id == user_id,
        Memory.embedding.isnot(None),
        Memory.status == "active",
        Memory.conflict_status == "active",
    ).limit(500)
    result = await db.execute(stmt)
    existing = result.scalars().all()

    best_sim = 0.0
    best_mem = None
    for mem in existing:
        sim = cosine_sim(embedding, mem.embedding)
        if sim > best_sim:
            best_sim = sim
            best_mem = mem

    if best_sim > 0.88 and best_mem:
        return ("duplicate", best_mem, None)
    elif best_sim > 0.80 and best_mem:
        chain_id = best_mem.chain_id or str(uuid.uuid4())
        return ("near_duplicate", best_mem, chain_id)
    return ("new", None, None)


# ========== Memory Decay ==========

async def compute_decay_scores(db: AsyncSession, org_id: str):
    """Recompute decay scores for all memories in an org."""
    stmt = select(Memory).where(Memory.org_id == org_id, Memory.status == "active")
    result = await db.execute(stmt)
    memories = result.scalars().all()
    now = datetime.utcnow()

    for mem in memories:
        last_access = mem.last_accessed_at or mem.created_at or now
        hours_since = max((now - last_access).total_seconds() / 3600, 0)
        base = mem.confidence or 1.0
        access = mem.access_count or 0
        score = base * math.exp(-DECAY_LAMBDA * hours_since) * (math.log(2 + access) / math.log(2))
        mem.decay_score = round(min(score, 1.0), 6)

    await db.commit()


async def decay_cleanup(db: AsyncSession, org_id: str, threshold: float = 0.1) -> int:
    """Archive memories with decay_score below threshold (soft delete)."""
    await compute_decay_scores(db, org_id)
    stmt = select(Memory).where(
        Memory.org_id == org_id,
        Memory.status == "active",
        Memory.decay_score < threshold,
    )
    result = await db.execute(stmt)
    memories = result.scalars().all()
    count = len(memories)
    for mem in memories:
        await log_audit(db, org_id, mem.id, "delete", actor_type="system", details={"reason": "decay_cleanup", "score": mem.decay_score})
        mem.status = "archived"
        await create_memory_event(db, org_id, mem.id, "archived", actor_type="system", source="decay_cleanup")
    await db.commit()
    return count


async def decay_preview(db: AsyncSession, org_id: str, limit: int = 100) -> List[Memory]:
    """Return memories sorted by decay score (lowest first)."""
    await compute_decay_scores(db, org_id)
    stmt = select(Memory).where(Memory.org_id == org_id, Memory.status == "active").order_by(Memory.decay_score.asc()).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# ========== Memory Chains ==========

async def get_chain(db: AsyncSession, chain_id: str) -> List[Memory]:
    """Get all memories in a chain."""
    stmt = select(Memory).where(Memory.chain_id == chain_id, Memory.status == "active").order_by(Memory.created_at)
    result = await db.execute(stmt)
    return result.scalars().all()


# ========== v0.4.0: Project & Task Management ==========

async def grant_pool_access_for_agents(
    db: AsyncSession,
    org_id: str,
    pool_id: str,
    agents: List[str],
):
    """Grant read+write pool access to a list of agents."""
    for agent_id in agents:
        # Check if access already exists
        stmt = select(PoolAccess).where(
            PoolAccess.org_id == org_id,
            PoolAccess.pool_id == pool_id,
            PoolAccess.agent_id == agent_id,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if not existing:
            access = PoolAccess(
                org_id=org_id,
                pool_id=pool_id,
                agent_id=agent_id,
                permissions={"read": True, "write": True, "admin": False},
            )
            db.add(access)


async def revoke_pool_access_for_agents(
    db: AsyncSession,
    org_id: str,
    pool_id: str,
    agents: List[str],
):
    """Revoke pool access for a list of agents."""
    for agent_id in agents:
        stmt = select(PoolAccess).where(
            PoolAccess.org_id == org_id,
            PoolAccess.pool_id == pool_id,
            PoolAccess.agent_id == agent_id,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            await db.delete(existing)


async def create_project(
    db: AsyncSession,
    org_id: str,
    name: str,
    slug: str,
    description: Optional[str] = None,
    agents: Optional[List[str]] = None,
    metadata: Optional[Dict] = None,
) -> Project:
    """Create a project with auto-generated pool_id and auto-granted access."""
    pool_id = f"project:{slug}"
    project = Project(
        org_id=org_id,
        name=name,
        slug=slug,
        pool_id=pool_id,
        description=description,
        agents=agents or [],
        metadata_=metadata or {},
    )
    db.add(project)
    await db.flush()

    # Auto-grant pool access to listed agents
    if agents:
        await grant_pool_access_for_agents(db, org_id, pool_id, agents)

    await db.commit()
    await db.refresh(project)
    return project


async def get_project(db: AsyncSession, project_id: str) -> Optional[Project]:
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def list_projects(db: AsyncSession, org_id: str) -> List[Project]:
    stmt = select(Project).where(Project.org_id == org_id).order_by(Project.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def update_project(
    db: AsyncSession,
    project_id: str,
    org_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    agents: Optional[List[str]] = None,
    status: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Optional[Project]:
    project = await get_project(db, project_id)
    if not project or project.org_id != org_id:
        return None

    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    if status is not None:
        project.status = status
    if metadata is not None:
        project.metadata_ = metadata

    # Handle agent list changes
    if agents is not None:
        old_agents = set(project.agents or [])
        new_agents = set(agents)
        added = new_agents - old_agents
        removed = old_agents - new_agents

        if added:
            await grant_pool_access_for_agents(db, org_id, project.pool_id, list(added))
        if removed:
            await revoke_pool_access_for_agents(db, org_id, project.pool_id, list(removed))

        project.agents = agents

    project.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(project)
    return project


async def archive_project(db: AsyncSession, project_id: str, org_id: str) -> Optional[Project]:
    project = await get_project(db, project_id)
    if not project or project.org_id != org_id:
        return None
    project.status = "archived"
    project.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(project)
    return project


async def get_memory_count_for_pool(db: AsyncSession, org_id: str, pool_id: str) -> int:
    stmt = select(func.count()).select_from(Memory).where(
        Memory.org_id == org_id,
        Memory.pool_id == pool_id,
        Memory.status == "active",
    )
    return (await db.execute(stmt)).scalar() or 0


async def get_recent_memories_for_pool(
    db: AsyncSession, org_id: str, pool_id: str, limit: int = 10
) -> List[Memory]:
    stmt = select(Memory).where(
        Memory.org_id == org_id,
        Memory.pool_id == pool_id,
        Memory.status == "active",
    ).order_by(Memory.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# Task management

async def create_task(
    db: AsyncSession,
    org_id: str,
    name: str,
    project_id: Optional[str] = None,
    agents: Optional[List[str]] = None,
    expires_in_hours: Optional[float] = None,
    metadata: Optional[Dict] = None,
) -> Task:
    slug = slugify(name)
    pool_id = f"task:{slug}"

    # Ensure unique pool_id
    existing = await db.execute(select(Task).where(Task.pool_id == pool_id))
    if existing.scalar_one_or_none():
        pool_id = f"task:{slug}-{str(uuid.uuid4())[:8]}"

    expires_at = None
    if expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)

    task = Task(
        org_id=org_id,
        project_id=project_id,
        name=name,
        pool_id=pool_id,
        agents=agents or [],
        expires_at=expires_at,
        metadata_=metadata or {},
    )
    db.add(task)
    await db.flush()

    if agents:
        await grant_pool_access_for_agents(db, org_id, pool_id, agents)

    await db.commit()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: str) -> Optional[Task]:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def list_tasks(
    db: AsyncSession,
    org_id: str,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> List[Task]:
    stmt = select(Task).where(Task.org_id == org_id)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if status:
        stmt = stmt.where(Task.status == status)
    # agent_id filter: check JSON array contains
    stmt = stmt.order_by(Task.created_at.desc())
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    if agent_id:
        tasks = [t for t in tasks if agent_id in (t.agents or [])]

    return tasks


async def update_task(
    db: AsyncSession,
    task_id: str,
    org_id: str,
    name: Optional[str] = None,
    agents: Optional[List[str]] = None,
    status: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Optional[Task]:
    task = await get_task(db, task_id)
    if not task or task.org_id != org_id:
        return None

    if name is not None:
        task.name = name
    if status is not None:
        task.status = status
    if metadata is not None:
        task.metadata_ = metadata

    if agents is not None:
        old_agents = set(task.agents or [])
        new_agents = set(agents)
        added = new_agents - old_agents
        removed = old_agents - new_agents

        if added:
            await grant_pool_access_for_agents(db, org_id, task.pool_id, list(added))
        if removed:
            await revoke_pool_access_for_agents(db, org_id, task.pool_id, list(removed))

        task.agents = agents

    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return task


async def archive_task(db: AsyncSession, task_id: str, org_id: str) -> Optional[Task]:
    task = await get_task(db, task_id)
    if not task or task.org_id != org_id:
        return None
    task.status = "archived"
    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return task


# ========== v0.4.0: Agent Context & Auto-Routing ==========

async def get_agent_context(db: AsyncSession, org_id: str, agent_id: str) -> Optional[AgentContext]:
    stmt = select(AgentContext).where(
        AgentContext.org_id == org_id,
        AgentContext.agent_id == agent_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def set_agent_context(
    db: AsyncSession,
    org_id: str,
    agent_id: str,
    active_project_id: Optional[str] = None,
    active_task_id: Optional[str] = None,
    default_scope: Optional[str] = None,
    default_pool_id: Optional[str] = None,
) -> AgentContext:
    ctx = await get_agent_context(db, org_id, agent_id)
    if not ctx:
        ctx = AgentContext(
            org_id=org_id,
            agent_id=agent_id,
        )
        db.add(ctx)

    if active_project_id is not None:
        ctx.active_project_id = active_project_id or None
    if active_task_id is not None:
        ctx.active_task_id = active_task_id or None
    if default_scope is not None:
        ctx.default_scope = default_scope
    if default_pool_id is not None:
        ctx.default_pool_id = default_pool_id or None

    ctx.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(ctx)
    return ctx


async def clear_agent_context(db: AsyncSession, org_id: str, agent_id: str) -> bool:
    ctx = await get_agent_context(db, org_id, agent_id)
    if not ctx:
        return False
    await db.delete(ctx)
    await db.commit()
    return True


async def resolve_agent_routing(
    db: AsyncSession,
    org_id: str,
    agent_id: Optional[str],
    pool_id: Optional[str] = None,
    scope: Optional[str] = None,
) -> tuple:
    """Resolve pool_id and scope based on agent context if not explicitly provided."""
    if pool_id and scope:
        return pool_id, scope  # Explicit = no auto-routing

    if not agent_id:
        return pool_id, scope or "private"

    # Look up agent context
    ctx = await get_agent_context(db, org_id, agent_id)
    if not ctx:
        return pool_id, scope or "private"

    if not pool_id:
        if ctx.active_task_id:
            task = await get_task(db, ctx.active_task_id)
            if task and task.status == "active":
                return task.pool_id, scope or "task"
        if ctx.active_project_id:
            project = await get_project(db, ctx.active_project_id)
            if project and project.status == "active":
                return project.pool_id, scope or "project"
        if ctx.default_pool_id:
            return ctx.default_pool_id, scope or ctx.default_scope or "team"

    return pool_id, scope or ctx.default_scope or "private"


# ========== Main Functions ==========

async def add_memory(
    db: AsyncSession,
    org_id: str,
    text: str,
    user_id: str,
    agent_id: Optional[str] = None,
    pool_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
    schema_id: Optional[str] = None,
    session_id_fk: Optional[str] = None,
    scope: str = "private",
    source_type: Optional[str] = None,
    source_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract memories from text and store them with dedup, instructions, audit, events."""

    # v0.4.0: Auto-routing — resolve pool_id and scope if not explicitly provided
    # Only auto-route when both pool_id and scope are at defaults
    if agent_id and not pool_id and scope == "private":
        pool_id, scope = await resolve_agent_routing(db, org_id, agent_id, pool_id, None)

    # Access control check
    if pool_id and agent_id:
        allowed = await check_pool_access(db, org_id, agent_id, pool_id, "write")
        if not allowed:
            return {"status": "error", "message": "Access denied to pool", "memories_created": 0, "counts": {}, "memory_ids": []}

    session_label = session_id or f"session_{int(time.time())}"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # Default source_type and source_ref
    effective_source_type = source_type or "extraction"
    effective_source_ref = source_ref or session_label

    # Fetch instructions
    instructions = await get_active_instructions(db, org_id, user_id)

    extractor = get_extractor()

    # If instructions exist, prepend them to the text for extraction
    extraction_text = text
    if instructions:
        instruction_block = "\n".join(f"- {inst}" for inst in instructions)
        extraction_text = f"[MEMORY INSTRUCTIONS - Follow these rules when extracting memories]\n{instruction_block}\n[END INSTRUCTIONS]\n\n{text}"

    extraction = extractor.extract(text=extraction_text, user_id=user_id, session_id=session_label, timestamp=timestamp)

    # If importance scoring filtered this out, return early
    if not extraction.triples and not extraction.summary and not extraction.temporal_events and not extraction.profile_attributes and extraction.importance < 1:
        return {
            "status": "skipped",
            "message": f"Content scored {extraction.importance}/5 importance — noise, not stored",
            "memories_created": 0,
            "counts": {},
            "memory_ids": [],
            "dedup_stats": None,
            "importance": extraction.importance,
            "categories": getattr(extraction, 'categories', []),
        }

    # Categories removed from extraction pipeline (v0.4.1)

    memory_ids = []
    counts = {"triples": 0, "summary": 0, "entities": 0, "temporal": 0, "profiles": 0, "raw": 1}
    dedup_stats = {"created": 0, "updated": 0, "chained": 0, "superseded": 0}
    chain_id_for_batch = str(uuid.uuid4())

    async def _store_memory(content: str, memory_type: str, structured_data=None, confidence=1.0):
        """Store a single memory with conflict-aware dedup logic."""
        emb = embed_text(content[:512])

        action, existing, chain_id = await _find_duplicate(db, org_id, user_id, content, emb)

        if action == "duplicate" and existing:
            # v0.3.0: Supersede instead of merge
            # Mark old memory as superseded
            existing.conflict_status = "superseded"
            existing.updated_at = datetime.utcnow()

            # Create new memory that supersedes the old one
            mem = Memory(
                org_id=org_id, user_id=user_id, agent_id=agent_id, pool_id=pool_id,
                memory_type=memory_type, content=content, embedding=emb,
                structured_data=structured_data, session_label=session_label,
                confidence=float(confidence),
                metadata_=metadata or {},
                decay_score=1.0,
                last_accessed_at=datetime.utcnow(),
                access_count=0,
                chain_id=existing.chain_id or chain_id_for_batch,
                schema_id=schema_id,
                session_id_fk=session_id_fk,
                status="active",
                scope=scope,
                conflict_status="active",
                supersedes_id=existing.id,
                version=(existing.version or 1) + 1,
                source_type=effective_source_type,
                source_ref=effective_source_ref,
                derived_from=[existing.id],
                
                importance=extraction.importance,
            )
            db.add(mem)
            await db.flush()

            # Create events
            await create_memory_event(
                db, org_id, existing.id, "superseded",
                actor_id=agent_id or user_id,
                actor_type="agent" if agent_id else "user",
                source=effective_source_type,
                previous_content=existing.content,
                new_content=content,
                metadata={"superseded_by": mem.id},
            )
            await create_memory_event(
                db, org_id, mem.id, "created",
                actor_id=agent_id or user_id,
                actor_type="agent" if agent_id else "user",
                source=effective_source_type,
                new_content=content,
                metadata={"supersedes": existing.id},
            )
            await log_audit(db, org_id, mem.id, "create", actor_id=agent_id or user_id, actor_type="agent" if agent_id else "user", details={"dedup": "superseded", "supersedes": existing.id})

            dedup_stats["superseded"] += 1
            memory_ids.append(mem.id)
            return mem

        mem = Memory(
            org_id=org_id, user_id=user_id, agent_id=agent_id, pool_id=pool_id,
            memory_type=memory_type, content=content, embedding=emb,
            structured_data=structured_data, session_label=session_label,
            confidence=float(confidence),
            metadata_=metadata or {},
            decay_score=1.0,
            last_accessed_at=datetime.utcnow(),
            access_count=0,
            chain_id=chain_id or chain_id_for_batch,
            schema_id=schema_id,
            session_id_fk=session_id_fk,
            status="active",
            scope=scope,
            conflict_status="active",
            version=1,
            source_type=effective_source_type,
            source_ref=effective_source_ref,
            
            importance=extraction.importance,
        )
        db.add(mem)
        await db.flush()

        # Create event
        await create_memory_event(
            db, org_id, mem.id, "created",
            actor_id=agent_id or user_id,
            actor_type="agent" if agent_id else "user",
            source=effective_source_type,
            new_content=content,
        )
        await log_audit(db, org_id, mem.id, "create", actor_id=agent_id or user_id, actor_type="agent" if agent_id else "user")

        if action == "near_duplicate":
            # Link the chain and mark potential conflict
            if existing and not existing.chain_id:
                existing.chain_id = chain_id
            mem_meta = mem.metadata_ or {}
            mem_meta["potential_conflict_with"] = existing.id if existing else None
            mem.metadata_ = mem_meta
            if existing:
                mem.derived_from = [existing.id]
            dedup_stats["chained"] += 1
        else:
            dedup_stats["created"] += 1

        memory_ids.append(mem.id)
        return mem

    # Store raw text
    await _store_memory(text[:512], "raw")

    # Store triples
    for triple in extraction.triples:
        content = f"{triple.get('subject', '')} {triple.get('predicate', '')} {triple.get('object', '')}"
        mem = await _store_memory(content, "triple", structured_data=triple, confidence=float(triple.get("confidence", 1.0)))
        counts["triples"] += 1

        # Store relation edge
        if triple.get("subject") and triple.get("object"):
            rel = Relation(
                org_id=org_id, user_id=user_id,
                source_entity=triple["subject"], relation=triple.get("predicate", ""),
                target_entity=triple["object"], memory_id=mem.id,
            )
            db.add(rel)

    # Store summary
    if extraction.summary:
        await _store_memory(extraction.summary[:512], "summary")
        counts["summary"] = 1

    # Store temporal events
    for event in extraction.temporal_events:
        content = f"{event.get('event', '')} {event.get('timestamp', '')} {event.get('absolute_date', '')}"
        await _store_memory(content[:512], "temporal", structured_data=event)
        counts["temporal"] += 1

    # Store profile attributes
    for attr in extraction.profile_attributes:
        content = f"{attr.get('person', '')} {attr.get('attribute', '')} {attr.get('value', '')}"
        await _store_memory(content[:512], "profile", structured_data=attr, confidence=float(attr.get("confidence", 1.0)))
        counts["profiles"] += 1

    await db.commit()

    # Fire webhooks
    await fire_webhooks(db, org_id, "memory.added", {
        "user_id": user_id, "agent_id": agent_id,
        "memories_created": len(memory_ids), "dedup_stats": dedup_stats,
    })

    return {
        "status": "ok",
        "memories_created": len(memory_ids),
        "counts": counts,
        "memory_ids": memory_ids,
        "dedup_stats": dedup_stats,
    }


async def search_memories(
    db: AsyncSession,
    org_id: str,
    query: str,
    user_id: str,
    agent_id: Optional[str] = None,
    pool_id: Optional[str] = None,
    search_scope: Optional[List[str]] = None,
    top_k: int = 10,
    agentic: bool = True,
) -> Dict[str, Any]:
    """Hybrid search: BM25 (FTS) + vector similarity + graph walk, RRF fusion.

    v0.3.0: scope-aware filtering, status=active only, provenance in results.
    v0.4.0: auto-routing for search when no explicit pool/scope given.
    """

    # v0.4.0: Auto-routing for search
    if agent_id and not pool_id and not search_scope:
        pool_id, _ = await resolve_agent_routing(db, org_id, agent_id, pool_id, None)

    # Access control check — for direct pool_id
    if pool_id and agent_id:
        allowed = await check_pool_access(db, org_id, agent_id, pool_id, "read")
        if not allowed:
            return {"memories": [], "context": "", "num_candidates": 0, "num_returned": 0}

    # Access control check — filter search_scope to allowed pools
    if search_scope and agent_id:
        allowed_scopes = []
        for scope in search_scope:
            if scope.startswith("shared:"):
                pool = scope.split(":", 1)[1]
                if await check_pool_access(db, org_id, agent_id, pool, "read"):
                    allowed_scopes.append(scope)
            else:
                allowed_scopes.append(scope)
        search_scope = allowed_scopes
        if not search_scope:
            return {"memories": [], "context": "", "num_candidates": 0, "num_returned": 0}

    # Build base filter — always filter active + non-superseded
    filters = [
        Memory.org_id == org_id,
        Memory.status == "active",
        Memory.conflict_status == "active",
    ]

    if search_scope:
        scope_filters = []
        for scope in search_scope:
            if scope.startswith("agent:"):
                scope_filters.append(Memory.agent_id == scope.split(":", 1)[1])
            elif scope.startswith("shared:"):
                scope_filters.append(Memory.pool_id == scope.split(":", 1)[1])
            elif scope.startswith("user:"):
                scope_filters.append(and_(Memory.user_id == scope.split(":", 1)[1]))
        if scope_filters:
            filters.append(or_(*scope_filters))
    else:
        # v0.4.1: Proper agent isolation
        # Each agent sees ONLY:
        # 1. Their own memories (agent_id match, any scope)
        # 2. Shared pool memories they have ACL access to
        # 3. Project/task pool memories they're assigned to
        # 4. Global scope memories
        visibility_filters = []

        if agent_id:
            # 1. Own memories (private or any scope)
            visibility_filters.append(Memory.agent_id == agent_id)

            # 2. Shared pools with ACL access — query allowed pools
            acl_stmt = select(PoolAccess.pool_id).where(
                PoolAccess.org_id == org_id,
                PoolAccess.agent_id == agent_id,
            )
            acl_result = await db.execute(acl_stmt)
            allowed_pools = [row[0] for row in acl_result.fetchall()]
            if allowed_pools:
                visibility_filters.append(Memory.pool_id.in_(allowed_pools))

            # 3. Global scope (visible to everyone in org)
            visibility_filters.append(Memory.scope == "global")
        else:
            # No agent specified — user-level access (own memories only)
            visibility_filters.append(Memory.user_id == user_id)

        # If specific pool requested, add it (ACL already checked above)
        if pool_id:
            visibility_filters.append(Memory.pool_id == pool_id)

        filters.append(or_(*visibility_filters))

    base_filter = and_(*filters)

    results = {}  # content -> result dict

    # 1. PostgreSQL FTS (BM25-like)
    fts_query = " & ".join(w for w in query.split() if len(w) > 2)
    if fts_query:
        fts_stmt = (
            select(Memory)
            .where(base_filter)
            .where(text("to_tsvector('english', content) @@ to_tsquery('english', :q)"))
            .params(q=fts_query)
            .limit(top_k * 3)
        )
        fts_rows = (await db.execute(fts_stmt)).scalars().all()
        for i, m in enumerate(fts_rows):
            results[m.id] = {
                "id": m.id, "content": m.content, "type": m.memory_type,
                "structured_data": m.structured_data, "bm25_rank": i + 1,
                "sources": ["bm25"], "confidence": m.confidence,
                "decay_score": m.decay_score, "importance": m.importance,
                "created_at": str(m.created_at),
                "scope": m.scope,
                "source_type": m.source_type,
                "source_ref": m.source_ref,
                "derived_from": m.derived_from,
            }

    # 2. Vector similarity search
    query_emb = embed_text(query[:512])
    vec_stmt = select(Memory).where(base_filter).where(Memory.embedding.isnot(None)).limit(500)
    vec_rows = (await db.execute(vec_stmt)).scalars().all()

    scored = []
    for m in vec_rows:
        sim = cosine_sim(query_emb, m.embedding)
        scored.append((sim, m))
    scored.sort(key=lambda x: x[0], reverse=True)

    for rank, (sim, m) in enumerate(scored[:top_k * 3]):
        if m.id in results:
            results[m.id]["sources"].append("vector")
            results[m.id]["vector_rank"] = rank + 1
            results[m.id]["vector_sim"] = sim
        else:
            results[m.id] = {
                "id": m.id, "content": m.content, "type": m.memory_type,
                "structured_data": m.structured_data, "vector_rank": rank + 1,
                "vector_sim": sim, "sources": ["vector"], "confidence": m.confidence,
                "decay_score": m.decay_score, "importance": m.importance,
                "created_at": str(m.created_at),
                "scope": m.scope,
                "source_type": m.source_type,
                "source_ref": m.source_ref,
                "derived_from": m.derived_from,
            }

    # 3. Graph walk via relations
    entities = _extract_query_entities_simple(query)
    for entity in entities[:5]:
        rel_stmt = select(Relation).where(
            Relation.org_id == org_id,
            Relation.user_id == user_id,
            or_(
                Relation.source_entity.ilike(f"%{entity}%"),
                Relation.target_entity.ilike(f"%{entity}%"),
            )
        ).limit(20)
        rels = (await db.execute(rel_stmt)).scalars().all()
        for rel in rels:
            if rel.memory_id and rel.memory_id not in results:
                mem_result = await db.execute(select(Memory).where(
                    Memory.id == rel.memory_id,
                    Memory.status == "active",
                    Memory.conflict_status == "active",
                ))
                mem = mem_result.scalar_one_or_none()
                if mem:
                    results[mem.id] = {
                        "id": mem.id, "content": mem.content, "type": mem.memory_type,
                        "structured_data": mem.structured_data,
                        "sources": ["graph"], "confidence": mem.confidence,
                        "decay_score": mem.decay_score, "importance": mem.importance,
                        "created_at": str(mem.created_at),
                        "scope": mem.scope,
                        "source_type": mem.source_type,
                        "source_ref": mem.source_ref,
                        "derived_from": mem.derived_from,
                    }

    # RRF fusion — pure relevance ranking
    # Only vector similarity + BM25 + decay. No entity keyword boost, no importance boost.
    # Importance controls write filtering (what to store), not read ranking (what to surface).
    # Categories are for dashboard visualization only, not retrieval.
    candidates = list(results.values())
    k = 60
    for c in candidates:
        score = 0.0
        if "bm25_rank" in c:
            score += 1.0 / (k + c["bm25_rank"])
        if "vector_rank" in c:
            score += 1.0 / (k + c["vector_rank"])
        # Multi-source bonus (found by both BM25 and vector = more confident)
        score += len(set(c["sources"])) * 0.1
        # Decay: frequently accessed memories stay strong
        decay = c.get("decay_score") or 1.0
        score *= decay
        c["rrf_score"] = score

    candidates.sort(key=lambda x: x["rrf_score"], reverse=True)
    candidates = candidates[:top_k * 2]

    # Agentic multi-round (optional)
    if agentic and candidates:
        candidates = await _agentic_retrieval(db, query, candidates, org_id, user_id, base_filter, top_k)

    # Truncate to top_k
    top = candidates[:top_k]

    # Update access tracking
    returned_ids = {m["id"] for m in top}
    if returned_ids:
        update_stmt = (
            update(Memory)
            .where(Memory.id.in_(returned_ids))
            .values(
                access_count=Memory.access_count + 1,
                last_accessed_at=datetime.utcnow(),
            )
        )
        await db.execute(update_stmt)
        await db.commit()

    # Assemble context
    context_lines = []
    for m in top:
        context_lines.append(f"[{m['type'].upper()}] {m['content']}")
    context = "\n".join(context_lines)

    return {
        "memories": top,
        "context": context,
        "num_candidates": len(candidates),
        "num_returned": len(top),
    }


async def _agentic_retrieval(db, query, candidates, org_id, user_id, base_filter, top_k):
    """One round of agentic sufficiency check + re-query."""
    docs_text = "\n".join(
        f"[{i+1}] ({c['type']}) {c['content']}" for i, c in enumerate(candidates[:15])
    )
    try:
        check_response = call_llm(
            prompt=SUFFICIENCY_CHECK_PROMPT.format(query=query, retrieved_docs=docs_text),
            provider="openrouter", model=LLM_MODEL, api_key=OPENROUTER_API_KEY,
        )
        import re
        json_match = re.search(r"\{.*\}", check_response, re.DOTALL)
        if json_match:
            check = json.loads(json_match.group())
            if check.get("is_sufficient", True):
                return candidates
    except Exception:
        return candidates

    return candidates


async def answer_question(
    db: AsyncSession,
    org_id: str,
    question: str,
    user_id: str,
    agent_id: Optional[str] = None,
    agentic: bool = True,
) -> Dict[str, Any]:
    """Search memories then generate an answer."""
    search_result = await search_memories(
        db, org_id, question, user_id, agent_id=agent_id, agentic=agentic,
    )
    context = search_result["context"]

    answer = call_llm(
        prompt=ANSWER_PROMPT.format(context=context, question=question),
        provider="openrouter", model=LLM_MODEL, api_key=OPENROUTER_API_KEY,
    )
    if "FINAL ANSWER:" in answer:
        answer = answer.split("FINAL ANSWER:")[-1].strip()

    return {
        "answer": answer,
        "memories_used": search_result["num_returned"],
        "context": context,
    }


async def list_memories(
    db: AsyncSession,
    org_id: str,
    user_id: str,
    agent_id: Optional[str] = None,
    pool_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    category: Optional[str] = None,
    scope: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Memory]:
    """List memories with filters. v0.3.0: status=active only, scope filter."""
    stmt = select(Memory).where(
        Memory.org_id == org_id,
        Memory.user_id == user_id,
        Memory.status == "active",
    )
    if agent_id:
        stmt = stmt.where(Memory.agent_id == agent_id)
    if pool_id:
        stmt = stmt.where(Memory.pool_id == pool_id)
    if memory_type:
        stmt = stmt.where(Memory.memory_type == memory_type)
    # Categories removed in v0.4.1 — parameter kept for backward compatibility but ignored
    if scope:
        stmt = stmt.where(Memory.scope == scope)
    stmt = stmt.order_by(Memory.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_memory(db: AsyncSession, memory_id: str, org_id: str) -> Optional[Memory]:
    result = await db.execute(select(Memory).where(Memory.id == memory_id, Memory.org_id == org_id))
    return result.scalar_one_or_none()


async def update_memory(db: AsyncSession, memory_id: str, org_id: str, content: Optional[str] = None, metadata: Optional[Dict] = None) -> Optional[Memory]:
    mem = await get_memory(db, memory_id, org_id)
    if not mem:
        return None

    previous_content = mem.content

    if content:
        mem.content = content
        mem.embedding = embed_text(content[:512])
    if metadata:
        mem.metadata_ = metadata

    await log_audit(db, org_id, memory_id, "update", actor_type="user", details={"content_changed": bool(content), "metadata_changed": bool(metadata)})

    # v0.3.0: Create event with previous content
    await create_memory_event(
        db, org_id, memory_id, "updated",
        actor_type="user",
        source="api",
        previous_content=previous_content if content else None,
        new_content=content,
    )

    await db.commit()
    await db.refresh(mem)

    await fire_webhooks(db, org_id, "memory.updated", {"memory_id": memory_id})

    return mem


async def delete_memory(db: AsyncSession, memory_id: str, org_id: str) -> bool:
    """v0.3.0: Soft delete — set status to archived instead of hard delete."""
    mem = await get_memory(db, memory_id, org_id)
    if not mem:
        return False

    await log_audit(db, org_id, memory_id, "delete", actor_type="user", details={"content": mem.content[:200]})

    # Soft delete
    mem.status = "archived"
    mem.updated_at = datetime.utcnow()

    # Create event
    await create_memory_event(
        db, org_id, memory_id, "archived",
        actor_type="user",
        source="api",
        previous_content=mem.content,
    )

    await db.commit()

    await fire_webhooks(db, org_id, "memory.deleted", {"memory_id": memory_id})

    return True


# ========== v0.3.0: Conflict Resolution ==========

async def get_memory_conflicts(db: AsyncSession, memory_id: str, org_id: str) -> List[Memory]:
    """Get memories that supersede or are superseded by this memory."""
    # Memories this one supersedes
    stmt1 = select(Memory).where(
        Memory.org_id == org_id,
        Memory.supersedes_id == memory_id,
    )
    # Memories that supersede this one (via superseded_by or supersedes_id)
    stmt2 = select(Memory).where(
        Memory.org_id == org_id,
        Memory.id == select(Memory.supersedes_id).where(Memory.id == memory_id).correlate(None).scalar_subquery(),
    )

    result1 = await db.execute(stmt1)
    result2 = await db.execute(stmt2)

    conflicts = list(result1.scalars().all()) + list(result2.scalars().all())

    # Also check the original memory's supersedes_id
    mem = await get_memory(db, memory_id, org_id)
    if mem and mem.supersedes_id:
        old = await get_memory(db, mem.supersedes_id, org_id)
        if old and old.id not in [c.id for c in conflicts]:
            conflicts.append(old)

    return conflicts


async def resolve_conflict(
    db: AsyncSession,
    memory_id: str,
    org_id: str,
    resolution: str,
    merged_content: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> Optional[Memory]:
    """Resolve a memory conflict."""
    mem = await get_memory(db, memory_id, org_id)
    if not mem:
        return None

    if resolution == "accept":
        # Accept this memory, mark conflicting ones as resolved
        mem.conflict_status = "active"
        # Mark all that this supersedes as fully resolved
        if mem.supersedes_id:
            old = await get_memory(db, mem.supersedes_id, org_id)
            if old:
                old.conflict_status = "superseded"
        await create_memory_event(db, org_id, memory_id, "updated", actor_id=actor_id, source="conflict_resolution", metadata={"resolution": "accept"})

    elif resolution == "reject":
        # Reject this memory, restore the old one
        mem.conflict_status = "superseded"
        mem.status = "archived"
        if mem.supersedes_id:
            old = await get_memory(db, mem.supersedes_id, org_id)
            if old:
                old.conflict_status = "active"
                old.status = "active"
        await create_memory_event(db, org_id, memory_id, "archived", actor_id=actor_id, source="conflict_resolution", metadata={"resolution": "reject"})

    elif resolution == "merge" and merged_content:
        # Merge: update this memory's content with merged version
        previous = mem.content
        mem.content = merged_content
        mem.embedding = embed_text(merged_content[:512])
        mem.conflict_status = "active"
        if mem.supersedes_id:
            old = await get_memory(db, mem.supersedes_id, org_id)
            if old:
                old.conflict_status = "superseded"
        await create_memory_event(
            db, org_id, memory_id, "updated",
            actor_id=actor_id, source="conflict_resolution",
            previous_content=previous, new_content=merged_content,
            metadata={"resolution": "merge"},
        )

    await db.commit()
    await db.refresh(mem)
    return mem


# ========== v0.3.0: Event History ==========

async def get_memory_history(db: AsyncSession, memory_id: str, org_id: str) -> List[MemoryEvent]:
    """Get all events for a memory."""
    stmt = select(MemoryEvent).where(
        MemoryEvent.org_id == org_id,
        MemoryEvent.memory_id == memory_id,
    ).order_by(MemoryEvent.created_at.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def list_events(
    db: AsyncSession,
    org_id: str,
    event_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    memory_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple:
    """List recent events with filters. Returns (events, total)."""
    stmt = select(MemoryEvent).where(MemoryEvent.org_id == org_id)
    count_stmt = select(func.count()).select_from(MemoryEvent).where(MemoryEvent.org_id == org_id)

    if event_type:
        stmt = stmt.where(MemoryEvent.event_type == event_type)
        count_stmt = count_stmt.where(MemoryEvent.event_type == event_type)
    if actor_id:
        stmt = stmt.where(MemoryEvent.actor_id == actor_id)
        count_stmt = count_stmt.where(MemoryEvent.actor_id == actor_id)
    if memory_id:
        stmt = stmt.where(MemoryEvent.memory_id == memory_id)
        count_stmt = count_stmt.where(MemoryEvent.memory_id == memory_id)

    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = stmt.order_by(MemoryEvent.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all(), total


# ========== v0.3.0: Subscriptions ==========

async def create_subscription(
    db: AsyncSession,
    org_id: str,
    agent_id: str,
    scope_filter: Optional[str] = None,
    pool_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    event_types: Optional[List[str]] = None,
) -> MemorySubscription:
    sub = MemorySubscription(
        org_id=org_id,
        agent_id=agent_id,
        scope_filter=scope_filter,
        pool_filter=pool_filter,
        category_filter=category_filter,
        event_types=event_types or ["created", "updated", "superseded"],
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


async def list_subscriptions(
    db: AsyncSession,
    org_id: str,
    agent_id: str,
) -> List[MemorySubscription]:
    stmt = select(MemorySubscription).where(
        MemorySubscription.org_id == org_id,
        MemorySubscription.agent_id == agent_id,
        MemorySubscription.is_active == True,
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_subscription(
    db: AsyncSession,
    sub_id: str,
    org_id: str,
) -> bool:
    result = await db.execute(select(MemorySubscription).where(
        MemorySubscription.id == sub_id,
        MemorySubscription.org_id == org_id,
    ))
    sub = result.scalar_one_or_none()
    if not sub:
        return False
    await db.delete(sub)
    await db.commit()
    return True


def _extract_query_entities_simple(query: str) -> List[str]:
    """Simple entity extraction from query."""
    skip = {"what", "when", "where", "who", "how", "why", "did", "does",
            "is", "are", "was", "were", "the", "a", "an", "in", "on",
            "at", "to", "for", "of", "with", "and", "or", "not", "has",
            "have", "had", "do", "will", "would", "could", "should",
            "about", "from", "by", "that", "this", "it", "they", "he",
            "she", "his", "her", "their", "its", "my", "your"}
    words = query.split()
    entities = []
    current = []
    for w in words:
        if w.lower() in skip:
            if current:
                entities.append(" ".join(current))
                current = []
            continue
        current.append(w.rstrip("?.,!"))
    if current:
        entities.append(" ".join(current))
    return [e for e in entities if len(e) > 1]
