"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  FolderKanban, Plus, Archive, Brain, CheckSquare, Users, Clock, Trash2,
} from "lucide-react";
import {
  getProjects, createProject, updateProject, getTasks, createTask, updateTask, getMemories,
} from "@/lib/api";
import { toast } from "sonner";

interface Project {
  id: string;
  name: string;
  slug: string;
  description?: string;
  pool_id?: string;
  agents?: string[];
  memory_count?: number;
  status?: string;
  created_at?: string;
}

interface Task {
  id: string;
  name: string;
  project_id?: string;
  pool_id?: string;
  agents?: string[];
  memory_count?: number;
  status?: string;
  expires_at?: string;
  created_at?: string;
}

interface Memory {
  id: string;
  content: string;
  memory_type: string;
  agent_id: string;
  created_at: string;
}

const statusColor: Record<string, string> = {
  active: "bg-green-500/20 text-green-400 border-green-500/30",
  archived: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
  completed: "bg-blue-500/20 text-blue-400 border-blue-500/30",
};

function slugify(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailProject, setDetailProject] = useState<Project | null>(null);
  const [detailTasks, setDetailTasks] = useState<Task[]>([]);
  const [detailMemories, setDetailMemories] = useState<Memory[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Create form
  const [newName, setNewName] = useState("");
  const [newSlug, setNewSlug] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newAgents, setNewAgents] = useState("");

  // New task form
  const [newTaskName, setNewTaskName] = useState("");
  const [newTaskAgents, setNewTaskAgents] = useState("");
  const [newTaskExpires, setNewTaskExpires] = useState("");

  // Edit agents
  const [editAgentsOpen, setEditAgentsOpen] = useState<Project | null>(null);
  const [editAgentsValue, setEditAgentsValue] = useState("");

  async function load() {
    try {
      const data = await getProjects();
      setProjects(Array.isArray(data) ? data : data.projects || data.items || []);
    } catch (e: unknown) {
      toast.error("Failed to load projects");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleCreate() {
    if (!newName.trim()) return;
    try {
      const agents = newAgents.split(",").map(a => a.trim()).filter(Boolean);
      await createProject({
        name: newName.trim(),
        slug: newSlug || slugify(newName),
        description: newDesc || undefined,
        agents: agents.length > 0 ? agents : undefined,
      });
      toast.success("Project created");
      setCreateOpen(false);
      setNewName(""); setNewSlug(""); setNewDesc(""); setNewAgents("");
      load();
    } catch {
      toast.error("Failed to create project");
    }
  }

  async function handleArchive(project: Project) {
    try {
      await updateProject(project.id, { status: "archived" });
      toast.success("Project archived");
      load();
    } catch {
      toast.error("Failed to archive project");
    }
  }

  async function openDetail(project: Project) {
    setDetailProject(project);
    setLoadingDetail(true);
    try {
      const [tasks, memories] = await Promise.allSettled([
        getTasks({ project_id: project.id }),
        project.pool_id ? getMemories({ pool_id: project.pool_id, limit: "10" }) : Promise.resolve([]),
      ]);
      const taskData = tasks.status === "fulfilled" ? tasks.value : [];
      const memData = memories.status === "fulfilled" ? memories.value : [];
      setDetailTasks(Array.isArray(taskData) ? taskData : taskData.tasks || taskData.items || []);
      setDetailMemories(Array.isArray(memData) ? memData : memData.memories || memData.items || []);
    } catch {
      // ignore
    } finally {
      setLoadingDetail(false);
    }
  }

  async function handleCreateTask() {
    if (!newTaskName.trim() || !detailProject) return;
    try {
      const agents = newTaskAgents.split(",").map(a => a.trim()).filter(Boolean);
      await createTask({
        name: newTaskName.trim(),
        project_id: detailProject.id,
        agents: agents.length > 0 ? agents : undefined,
        expires_in_hours: newTaskExpires ? parseInt(newTaskExpires) : undefined,
      });
      toast.success("Task created");
      setNewTaskName(""); setNewTaskAgents(""); setNewTaskExpires("");
      openDetail(detailProject);
    } catch {
      toast.error("Failed to create task");
    }
  }

  async function handleTaskAction(task: Task, status: string) {
    try {
      await updateTask(task.id, { status });
      toast.success(`Task ${status}`);
      if (detailProject) openDetail(detailProject);
    } catch {
      toast.error("Failed to update task");
    }
  }

  async function handleSaveAgents() {
    if (!editAgentsOpen) return;
    try {
      const agents = editAgentsValue.split(",").map(a => a.trim()).filter(Boolean);
      await updateProject(editAgentsOpen.id, { agents });
      toast.success("Agents updated");
      setEditAgentsOpen(null);
      load();
    } catch {
      toast.error("Failed to update agents");
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <FolderKanban className="h-6 w-6 text-primary" />
            Projects
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage projects, tasks, and agent assignments
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="gap-2">
          <Plus className="h-4 w-4" /> New Project
        </Button>
      </div>

      {/* Project Cards */}
      {loading ? (
        <div className="text-muted-foreground text-sm">Loading projects…</div>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <FolderKanban className="h-12 w-12 mx-auto mb-4 opacity-30" />
            <p>No projects yet. Create one to get started.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Card
              key={project.id}
              className="cursor-pointer hover:border-primary/50 transition-colors group"
              onClick={() => openDetail(project)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <CardTitle className="text-base flex items-center gap-2">
                    <FolderKanban className="h-4 w-4 text-primary" />
                    {project.name}
                  </CardTitle>
                  <Badge variant="outline" className={statusColor[project.status || "active"]}>
                    {project.status || "active"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {project.description && (
                  <p className="text-sm text-muted-foreground line-clamp-2">{project.description}</p>
                )}

                {/* Memory count */}
                <div className="flex items-center gap-2 text-sm">
                  <Brain className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="font-semibold text-foreground">{project.memory_count ?? 0}</span>
                  <span className="text-muted-foreground">memories</span>
                </div>

                {/* Pool */}
                {project.pool_id && (
                  <p className="text-xs text-muted-foreground font-mono">pool: {project.pool_id}</p>
                )}

                {/* Agents */}
                {project.agents && project.agents.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {project.agents.map((agent) => (
                      <Badge key={agent} variant="outline" className="bg-purple-500/20 text-purple-400 border-purple-500/30 text-xs">
                        {agent}
                      </Badge>
                    ))}
                  </div>
                )}

                {/* Date + actions */}
                <div className="flex items-center justify-between pt-1">
                  <span className="text-xs text-muted-foreground">
                    {project.created_at ? new Date(project.created_at).toLocaleDateString() : "—"}
                  </span>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      title="Edit agents"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditAgentsValue((project.agents || []).join(", "));
                        setEditAgentsOpen(project);
                      }}
                    >
                      <Users className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      title="Archive"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleArchive(project);
                      }}
                    >
                      <Archive className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create Project Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Project</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Name</label>
              <Input
                value={newName}
                onChange={(e) => {
                  setNewName(e.target.value);
                  setNewSlug(slugify(e.target.value));
                }}
                placeholder="My Project"
              />
            </div>
            <div>
              <label className="text-sm font-medium">Slug</label>
              <Input
                value={newSlug}
                onChange={(e) => setNewSlug(e.target.value)}
                placeholder="my-project"
                className="font-mono text-sm"
              />
            </div>
            <div>
              <label className="text-sm font-medium">Description</label>
              <Textarea
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Optional description…"
                rows={2}
              />
            </div>
            <div>
              <label className="text-sm font-medium">Agents (comma-separated)</label>
              <Input
                value={newAgents}
                onChange={(e) => setNewAgents(e.target.value)}
                placeholder="agent-1, agent-2"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!newName.trim()}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Agents Dialog */}
      <Dialog open={!!editAgentsOpen} onOpenChange={(open) => !open && setEditAgentsOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Agents — {editAgentsOpen?.name}</DialogTitle>
          </DialogHeader>
          <div>
            <label className="text-sm font-medium">Agents (comma-separated)</label>
            <Input
              value={editAgentsValue}
              onChange={(e) => setEditAgentsValue(e.target.value)}
              placeholder="agent-1, agent-2"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditAgentsOpen(null)}>Cancel</Button>
            <Button onClick={handleSaveAgents}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Project Detail Dialog */}
      <Dialog open={!!detailProject} onOpenChange={(open) => !open && setDetailProject(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          {detailProject && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <FolderKanban className="h-5 w-5 text-primary" />
                  {detailProject.name}
                  <Badge variant="outline" className={statusColor[detailProject.status || "active"]}>
                    {detailProject.status || "active"}
                  </Badge>
                </DialogTitle>
              </DialogHeader>

              <div className="space-y-6">
                {/* Info */}
                <div className="space-y-2 text-sm">
                  {detailProject.description && <p className="text-muted-foreground">{detailProject.description}</p>}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div><span className="text-muted-foreground">Slug:</span> <span className="font-mono">{detailProject.slug}</span></div>
                    <div><span className="text-muted-foreground">Pool:</span> <span className="font-mono">{detailProject.pool_id || "—"}</span></div>
                    <div><span className="text-muted-foreground">Memories:</span> <span className="font-semibold">{detailProject.memory_count ?? 0}</span></div>
                    <div><span className="text-muted-foreground">Created:</span> {detailProject.created_at ? new Date(detailProject.created_at).toLocaleString() : "—"}</div>
                  </div>
                  {detailProject.agents && detailProject.agents.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {detailProject.agents.map((a) => (
                        <Badge key={a} variant="outline" className="bg-purple-500/20 text-purple-400 border-purple-500/30 text-xs">{a}</Badge>
                      ))}
                    </div>
                  )}
                </div>

                {/* Recent Memories */}
                <div>
                  <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <Brain className="h-4 w-4" /> Recent Memories
                  </h3>
                  {loadingDetail ? (
                    <p className="text-xs text-muted-foreground">Loading…</p>
                  ) : detailMemories.length === 0 ? (
                    <p className="text-xs text-muted-foreground">No memories in this pool yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {detailMemories.map((m) => (
                        <div key={m.id} className="rounded-md border border-border p-2 text-xs">
                          <p className="line-clamp-2">{m.content}</p>
                          <p className="text-muted-foreground mt-1">{m.agent_id} · {m.memory_type} · {new Date(m.created_at).toLocaleString()}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Tasks */}
                <div>
                  <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <CheckSquare className="h-4 w-4" /> Tasks
                  </h3>
                  {loadingDetail ? (
                    <p className="text-xs text-muted-foreground">Loading…</p>
                  ) : (
                    <div className="space-y-2">
                      {detailTasks.length === 0 && (
                        <p className="text-xs text-muted-foreground">No tasks yet.</p>
                      )}
                      {detailTasks.map((task) => (
                        <div key={task.id} className="rounded-md border border-border p-3 flex items-start justify-between gap-2">
                          <div className="space-y-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <CheckSquare className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                              <span className="text-sm font-medium truncate">{task.name}</span>
                              <Badge variant="outline" className={statusColor[task.status || "active"] + " text-xs"}>
                                {task.status || "active"}
                              </Badge>
                            </div>
                            <div className="flex flex-wrap gap-1">
                              {task.agents?.map((a) => (
                                <Badge key={a} variant="outline" className="bg-purple-500/20 text-purple-400 border-purple-500/30 text-[10px]">{a}</Badge>
                              ))}
                            </div>
                            <div className="text-xs text-muted-foreground flex gap-3">
                              {task.pool_id && <span className="font-mono">pool: {task.pool_id}</span>}
                              <span><Brain className="h-3 w-3 inline" /> {task.memory_count ?? 0}</span>
                              {task.expires_at && (
                                <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(task.expires_at).toLocaleString()}</span>
                              )}
                            </div>
                          </div>
                          <div className="flex gap-1 flex-shrink-0">
                            {task.status !== "completed" && (
                              <Button variant="ghost" size="icon" className="h-7 w-7" title="Complete" onClick={() => handleTaskAction(task, "completed")}>
                                <CheckSquare className="h-3.5 w-3.5 text-blue-400" />
                              </Button>
                            )}
                            {task.status !== "archived" && (
                              <Button variant="ghost" size="icon" className="h-7 w-7" title="Archive" onClick={() => handleTaskAction(task, "archived")}>
                                <Archive className="h-3.5 w-3.5" />
                              </Button>
                            )}
                          </div>
                        </div>
                      ))}

                      {/* New Task */}
                      <div className="rounded-md border border-dashed border-border p-3 space-y-2">
                        <p className="text-xs font-medium text-muted-foreground">New Task</p>
                        <div className="flex gap-2">
                          <Input
                            value={newTaskName}
                            onChange={(e) => setNewTaskName(e.target.value)}
                            placeholder="Task name"
                            className="text-sm h-8"
                          />
                          <Input
                            value={newTaskAgents}
                            onChange={(e) => setNewTaskAgents(e.target.value)}
                            placeholder="Agents"
                            className="text-sm h-8 w-32"
                          />
                          <Input
                            value={newTaskExpires}
                            onChange={(e) => setNewTaskExpires(e.target.value)}
                            placeholder="Hours"
                            type="number"
                            className="text-sm h-8 w-20"
                          />
                          <Button size="sm" className="h-8" onClick={handleCreateTask} disabled={!newTaskName.trim()}>
                            <Plus className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
