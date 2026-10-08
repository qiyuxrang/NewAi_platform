import { Shield, AlertTriangle, Info, CheckCircle } from 'lucide-react'

const logs = [
  { id: 1, time: '10:32:15', level: 'info', agent: 'Nova-Alpha 01', action: '完成市场调研报告生成', detail: '生成 PDF 报告并发送至企业微信' },
  { id: 2, time: '10:28:03', level: 'warning', agent: 'DevOps-Bot 02', action: 'CPU 使用率超过阈值', detail: '服务器 prod-web-03 CPU 达到 92%' },
  { id: 3, time: '10:15:47', level: 'info', agent: 'Sales-AI 03', action: '客户方案生成完成', detail: '为客户 #A2089 生成定制方案' },
  { id: 4, time: '09:50:22', level: 'info', agent: 'Doc-Parser 04', action: '合同解析完成', detail: '成功提取 23 个关键条款' },
  { id: 5, time: '09:30:11', level: 'security', agent: 'Security-Guard 05', action: '异常登录检测', detail: '来自未知 IP 的登录尝试已拦截' },
  { id: 6, time: '09:15:00', level: 'info', agent: '系统', action: '每日数据备份完成', detail: '备份大小 2.3 GB' },
  { id: 7, time: '09:00:05', level: 'warning', agent: 'Sales-AI 03', action: '响应延迟超过阈值', detail: '平均响应时间 1.8s，阈值 1.5s' },
  { id: 8, time: '08:45:30', level: 'info', agent: 'DevOps-Bot 02', action: '流水线部署成功', detail: 'v2.3.1 已部署至 staging 环境' },
]

const levelConfig = {
  info: { icon: Info, color: 'text-accent-blue', bg: 'bg-accent-blue/10' },
  warning: { icon: AlertTriangle, color: 'text-accent-yellow', bg: 'bg-accent-yellow/10' },
  security: { icon: Shield, color: 'text-accent-red', bg: 'bg-accent-red/10' },
  success: { icon: CheckCircle, color: 'text-accent-green', bg: 'bg-accent-green/10' },
}

export default function AuditLog() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-dark-text">审计日志</h1>
        <p className="mt-1 text-sm text-dark-text-secondary">系统操作和安全事件记录</p>
      </div>

      <div className="space-y-2">
        {logs.map(log => {
          const config = levelConfig[log.level as keyof typeof levelConfig] || levelConfig.info
          const Icon = config.icon
          return (
            <div key={log.id} className="flex items-start gap-4 rounded-xl border border-dark-border bg-dark-card p-4 hover:bg-dark-card-hover transition-colors">
              <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${config.bg}`}>
                <Icon size={16} className={config.color} />
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-dark-text">{log.action}</div>
                  <span className="text-xs text-dark-text-secondary">今天 {log.time}</span>
                </div>
                <div className="mt-0.5 text-xs text-dark-text-secondary">{log.detail}</div>
                <div className="mt-1 text-xs text-dark-text-secondary/70">来源: {log.agent}</div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
