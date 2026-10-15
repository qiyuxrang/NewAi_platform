import type { BusinessAssignment, BusinessRole, DepartmentCode } from "@/types";

export const businessRoleLabels: Record<BusinessRole, string> = {
  unassigned: "未分配", employee: "部门员工", general_manager: "总经理",
};
export const departmentLabels: Record<DepartmentCode, string> = {
  product: "产品事业部", hr: "人事部", engineering: "工程部", finance: "财务部",
};

export function businessAssignmentPayload(
  role: BusinessRole, department: DepartmentCode | "none", portalUserId: string,
): BusinessAssignment {
  const departmentCode = role === "unassigned" || department === "none" ? null : department;
  if (role === "employee" && departmentCode === null) {
    throw new Error("请为部门员工选择所属部门。");
  }
  const trimmedId = portalUserId.trim();
  const identifier = trimmedId ? Number(trimmedId) : null;
  if (identifier !== null && (!/^\d+$/.test(trimmedId) || !Number.isSafeInteger(identifier) || identifier <= 0)) {
    throw new Error("原业务用户 ID 必须是正整数，留空表示未关联。");
  }
  return { business_role: role, department_code: departmentCode, portal_user_id: identifier };
}

export function userCredentialsPayload(username: string, email: string, password: string) {
  const normalizedUsername = username.trim();
  const normalizedEmail = email.trim();
  if (!normalizedUsername || Array.from(normalizedUsername).length > 64 || /[\s\x00-\x1f\x7f]/u.test(normalizedUsername)) {
    throw new Error("用户名须为 1 至 64 个字符，不能包含空白或控制字符。");
  }
  if (normalizedEmail.length > 256 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(normalizedEmail)) {
    throw new Error("请填写有效邮箱。");
  }
  if (Array.from(password).length < 8 || new TextEncoder().encode(password).byteLength > 72) {
    throw new Error("密码须至少 8 个字符，且不超过 72 个 UTF-8 字节。");
  }
  return { username: normalizedUsername, email: normalizedEmail, password };
}
