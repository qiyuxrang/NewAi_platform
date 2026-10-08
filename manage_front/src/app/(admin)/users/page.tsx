"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { createUser, getUsers, updateUser, resetPassword } from "@/lib/api";
import { businessAssignmentPayload, businessRoleLabels, departmentLabels, userCredentialsPayload } from "@/lib/business-assignment";
import type { BusinessRole, DepartmentCode, UserSummary, PaginatedUsers } from "@/types";
import { toast } from "sonner";

export default function UsersPage() {
  const [data, setData] = useState<PaginatedUsers | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");

  // Edit dialog
  const [editUser, setEditUser] = useState<UserSummary | null>(null);
  const [editRole, setEditRole] = useState("");
  const [editTier, setEditTier] = useState("");
  //dedicated表示独立容器模式，shared表示共享容器模式
  const [editRuntimeMode, setEditRuntimeMode] = useState("dedicated");
  const [editActive, setEditActive] = useState(true);
  const [editBusinessRole, setEditBusinessRole] = useState<BusinessRole>("unassigned");
  const [editDepartment, setEditDepartment] = useState<DepartmentCode | "none">("none");
  const [editPortalUserId, setEditPortalUserId] = useState("");
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createUsername, setCreateUsername] = useState("");
  const [createEmail, setCreateEmail] = useState("");
  const [createPassword, setCreatePassword] = useState("");

  // Password dialog
  const [pwdUser, setPwdUser] = useState<UserSummary | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getUsers(page, 20, search);
      setData(result);
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  function openEdit(user: UserSummary) {
    setCreateOpen(false);
    setEditUser(user);
    setEditRole(user.role);
    setEditTier(user.quota_tier);
    setEditRuntimeMode(user.runtime_mode || "dedicated");
    setEditActive(user.is_active);
    setEditBusinessRole(user.business_role || "unassigned");
    setEditDepartment(user.department_code || "none");
    setEditPortalUserId(user.portal_user_id === null || user.portal_user_id === undefined ? "" : String(user.portal_user_id));
  }

  function openCreate() {
    setEditUser(null);
    setEditRole("user");
    setEditTier("free");
    setEditRuntimeMode("dedicated");
    setEditActive(true);
    setEditBusinessRole("unassigned");
    setEditDepartment("none");
    setEditPortalUserId("");
    setCreateUsername("");
    setCreateEmail("");
    setCreatePassword("");
    setCreateOpen(true);
  }

  function closeUserDialog() {
    setCreateOpen(false);
    setEditUser(null);
    setCreatePassword("");
  }

  async function handleSaveEdit() {
    if ((!editUser && !createOpen) || saving) return;
    setSaving(true);
    try {
      const payload = {
        role: editRole,
        quota_tier: editTier,
        runtime_mode: editRuntimeMode,
        is_active: editActive,
        ...businessAssignmentPayload(editBusinessRole, editDepartment, editPortalUserId),
      };
      if (createOpen) {
        await createUser({ ...payload, ...userCredentialsPayload(createUsername, createEmail, createPassword) });
      } else if (editUser) {
        await updateUser(editUser.id, payload);
      }
      toast.success(createOpen ? "用户已创建" : "用户已更新");
      closeUserDialog();
      fetchUsers();
    } catch (err) {
      toast.error(createOpen ? "创建失败" : "更新失败", { description: err instanceof Error ? err.message : "" });
    } finally {
      setSaving(false);
    }
  }

  async function handleResetPassword() {
    if (!pwdUser) return;
    if (newPassword.length < 8) {
      toast.error("密码至少8位");
      return;
    }
    try {
      await resetPassword(pwdUser.id, newPassword);
      toast.success("密码已重置");
      setPwdUser(null);
      setNewPassword("");
    } catch (err) {
      toast.error("重置失败", { description: err instanceof Error ? err.message : "" });
    }
  }

  const totalPages = data ? Math.ceil(data.total / 20) : 0;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">用户管理</h2>

      <div className="mb-4 flex items-center justify-between gap-4">
        <Input
          placeholder="搜索用户名或邮箱..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="max-w-sm"
        />
        <Button onClick={openCreate}>创建账号</Button>
      </div>

      {loading ? (
        <p className="text-gray-500">加载中...</p>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用户名</TableHead>
                <TableHead>邮箱</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>业务身份</TableHead>
                <TableHead>所属部门</TableHead>
                <TableHead>原业务用户 ID</TableHead>
                <TableHead>配额</TableHead>
                <TableHead>运行模式</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>今日用量</TableHead>
                <TableHead>近7天用量</TableHead>
                <TableHead>总用量</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.items.map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium">{user.username}</TableCell>
                  <TableCell>{user.email}</TableCell>
                  <TableCell>
                    <Badge variant={user.role === "admin" ? "default" : "secondary"}>
                      {user.role}
                    </Badge>
                  </TableCell>
                  <TableCell>{businessRoleLabels[user.business_role || "unassigned"]}</TableCell>
                  <TableCell>{user.department_code ? departmentLabels[user.department_code] : "未分配"}</TableCell>
                  <TableCell>{user.portal_user_id ?? "未关联"}</TableCell>
                  <TableCell>{user.quota_tier}</TableCell>
                  <TableCell>
                    <Badge variant={user.runtime_mode === "shared" ? "secondary" : "outline"}>
                      {user.runtime_mode}
                    </Badge>
                    {user.shared_agent_id ? (
                      <div className="text-xs text-muted-foreground mt-1">
                        {user.shared_agent_id}
                      </div>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Badge variant={user.is_active ? "default" : "destructive"}>
                      {user.is_active ? "正常" : "禁用"}
                    </Badge>
                  </TableCell>
                  <TableCell>{user.tokens_used_today.toLocaleString()}</TableCell>
                  <TableCell>{user.tokens_used_7d.toLocaleString()}</TableCell>
                  <TableCell>{user.tokens_used_total.toLocaleString()}</TableCell>
                  <TableCell>{user.created_at ? new Date(user.created_at).toLocaleDateString() : "-"}</TableCell>
                  <TableCell className="space-x-2">
                    <Button size="sm" variant="outline" onClick={() => openEdit(user)}>编辑</Button>
                    <Button size="sm" variant="outline" onClick={() => setPwdUser(user)}>重置密码</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-gray-500">共 {data?.total ?? 0} 个用户</p>
            <div className="space-x-2">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
              <span className="text-sm">{page} / {totalPages}</span>
              <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</Button>
            </div>
          </div>
        </>
      )}

      {/* Edit Dialog */}
      <Dialog open={!!editUser || createOpen} onOpenChange={(open) => !open && !saving && closeUserDialog()}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{createOpen ? "创建账号" : `编辑用户: ${editUser?.username}`}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {createOpen && <>
              <div><Label htmlFor="create-username">用户名</Label><Input id="create-username" value={createUsername} disabled={saving}
                autoComplete="off" onChange={event => setCreateUsername(event.target.value)} placeholder="1 至 64 个字符，不含空白" /></div>
              <div><Label htmlFor="create-email">邮箱</Label><Input id="create-email" type="email" value={createEmail} disabled={saving}
                autoComplete="off" onChange={event => setCreateEmail(event.target.value)} /></div>
              <div><Label htmlFor="create-password">初始密码</Label><Input id="create-password" type="password" value={createPassword} disabled={saving}
                autoComplete="new-password" onChange={event => setCreatePassword(event.target.value)} placeholder="至少 8 个字符" /></div>
            </>}
            <div>
              <Label>角色</Label>
              <Select value={editRole} onValueChange={(v: string | null) => v && setEditRole(v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">user</SelectItem>
                  <SelectItem value="admin">admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>配额等级</Label>
              <Select value={editTier} onValueChange={(v: string | null) => v && setEditTier(v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="free">free</SelectItem>
                  <SelectItem value="basic">basic</SelectItem>
                  <SelectItem value="pro">pro</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>运行模式</Label>
              <Select value={editRuntimeMode} onValueChange={(v: string | null) => v && setEditRuntimeMode(v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="dedicated">dedicated</SelectItem>
                  <SelectItem value="shared">shared</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Label>账号状态</Label>
              <Select value={editActive ? "active" : "disabled"} onValueChange={(v: string | null) => setEditActive(v === "active")}>
                <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">正常</SelectItem>
                  <SelectItem value="disabled">禁用</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-4 border-t pt-4">
              <div>
                <Label htmlFor="business-role">业务身份</Label>
                <Select value={editBusinessRole} disabled={saving} onValueChange={(value: string | null) => {
                  if (value === "unassigned" || value === "employee" || value === "general_manager") {
                    setEditBusinessRole(value);
                    if (value === "unassigned") setEditDepartment("none");
                  }
                }}>
                  <SelectTrigger id="business-role"><SelectValue>{businessRoleLabels[editBusinessRole]}</SelectValue></SelectTrigger>
                  <SelectContent>
                    {Object.entries(businessRoleLabels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="business-department">所属部门</Label>
                <Select value={editDepartment} disabled={saving || editBusinessRole === "unassigned"} onValueChange={(value: string | null) => {
                  if (value === "none" || value === "product" || value === "hr" || value === "engineering") setEditDepartment(value);
                }}>
                  <SelectTrigger id="business-department"><SelectValue>{editDepartment === "none" ? "未分配" : departmentLabels[editDepartment]}</SelectValue></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">未分配</SelectItem>
                    {Object.entries(departmentLabels).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="portal-user-id">原业务用户 ID</Label>
                <Input id="portal-user-id" inputMode="numeric" value={editPortalUserId} disabled={saving}
                  onChange={event => setEditPortalUserId(event.target.value)} placeholder="正整数，留空表示未关联" />
              </div>
              <p className="text-xs text-muted-foreground">{createOpen ? "用户创建后需登录并连接本人业务账号。" : "变更业务身份、部门或原业务用户 ID 后，用户需重新连接业务账号。"}</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={saving} onClick={closeUserDialog}>取消</Button>
            <Button disabled={saving} onClick={handleSaveEdit}>{saving ? "保存中…" : createOpen ? "创建" : "保存"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Password Reset Dialog */}
      <Dialog open={!!pwdUser} onOpenChange={(open) => { if (!open) { setPwdUser(null); setNewPassword(""); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>重置密码: {pwdUser?.username}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label>新密码</Label>
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="至少8位"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setPwdUser(null); setNewPassword(""); }}>取消</Button>
            <Button onClick={handleResetPassword}>确认重置</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
