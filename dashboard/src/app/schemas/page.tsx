"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Trash2, X } from "lucide-react";
import { getSchemas, createSchema, deleteSchema } from "@/lib/api";
import { toast } from "sonner";

interface SchemaField {
  name: string;
  type: string;
  required: boolean;
}

interface SchemaEntry {
  id: string;
  name: string;
  description: string;
  fields: SchemaField[];
  created_at: string;
}

const FIELD_TYPES = ["string", "number", "boolean", "array", "object", "date"];

export default function SchemasPage() {
  const [schemas, setSchemas] = useState<SchemaEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", description: "", fields: [{ name: "", type: "string", required: false }] as SchemaField[] });

  const load = async () => {
    setLoading(true);
    try {
      const res = await getSchemas();
      setSchemas(res.schemas || res || []);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const addField = () => setForm((f) => ({ ...f, fields: [...f.fields, { name: "", type: "string", required: false }] }));
  const removeField = (i: number) => setForm((f) => ({ ...f, fields: f.fields.filter((_, idx) => idx !== i) }));
  const updateField = (i: number, patch: Partial<SchemaField>) => {
    setForm((f) => ({ ...f, fields: f.fields.map((field, idx) => idx === i ? { ...field, ...patch } : field) }));
  };

  const handleCreate = async () => {
    try {
      await createSchema({
        name: form.name,
        fields: form.fields.filter((f) => f.name),
        description: form.description || undefined,
      });
      toast.success("Schema created");
      setShowCreate(false);
      setForm({ name: "", description: "", fields: [{ name: "", type: "string", required: false }] });
      load();
    } catch { toast.error("Failed to create schema"); }
  };

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteSchema(deleteId);
      toast.success("Schema deleted");
      setDeleteId(null);
      load();
    } catch { toast.error("Failed to delete"); }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Schemas</h1>
          <p className="text-muted-foreground">Define memory structure templates</p>
        </div>
        <Button size="sm" className="gap-1.5" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" /> New Schema
        </Button>
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/30">
              <TableHead className="text-xs font-medium">Name</TableHead>
              <TableHead className="text-xs font-medium">Description</TableHead>
              <TableHead className="w-24 text-xs font-medium">Fields</TableHead>
              <TableHead className="w-40 text-xs font-medium">Created</TableHead>
              <TableHead className="w-16 text-xs font-medium" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={5} className="text-center py-12 text-muted-foreground">Loading...</TableCell></TableRow>
            ) : schemas.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="text-center py-12 text-muted-foreground">No schemas</TableCell></TableRow>
            ) : (
              schemas.map((s) => (
                <TableRow key={s.id} className="group">
                  <TableCell className="text-sm font-medium">{s.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground truncate max-w-xs">{s.description || "—"}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="text-[11px]">{s.fields?.length || 0} fields</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{new Date(s.created_at).toLocaleDateString()}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" className="h-7 w-7 opacity-0 group-hover:opacity-100" onClick={() => setDeleteId(s.id)}>
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Create Schema</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input placeholder="Schema name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Input placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-medium">Fields</p>
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={addField}>+ Add Field</Button>
              </div>
              <div className="space-y-2">
                {form.fields.map((field, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input
                      placeholder="Field name"
                      value={field.name}
                      onChange={(e) => updateField(i, { name: e.target.value })}
                      className="h-8 text-sm"
                    />
                    <select
                      value={field.type}
                      onChange={(e) => updateField(i, { type: e.target.value })}
                      className="h-8 rounded-md border border-border bg-background px-2 text-sm"
                    >
                      {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <label className="flex items-center gap-1 text-xs text-muted-foreground whitespace-nowrap">
                      <input type="checkbox" checked={field.required} onChange={(e) => updateField(i, { required: e.target.checked })} />
                      Req
                    </label>
                    <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => removeField(i)}>
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!form.name}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!deleteId} onOpenChange={() => setDeleteId(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete Schema</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Are you sure? This cannot be undone.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteId(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
