import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { listRuntimeModels, type AgentInfo, type ModelChoice } from '../lib/api'
import type { SlashCommandItem } from '../lib/slashCommands'

export default function ComposerTools({ disabled, commands, agents, onFiles, onCommand, onExpert, model, onModel }: {
  disabled: boolean
  commands: SlashCommandItem[]
  agents: AgentInfo[]
  onFiles: () => void
  onCommand: (command: SlashCommandItem) => void
  onExpert: (agentId: string) => void
  model: string
  onModel: (model: string) => void
}) {
  const menu = useRef<HTMLDetailsElement>(null)
  const [models, setModels] = useState<ModelChoice[]>([])
  const [modelError, setModelError] = useState('')
  const [defaultModel, setDefaultModel] = useState('')
  useEffect(() => {
    let active = true
    listRuntimeModels().then(result => {
      if (active) { setModels(result.models); setDefaultModel(result.configuredModel) }
    }).catch(error => { if (active) setModelError(error.message || '无法加载模型') })
    return () => { active = false }
  }, [])
  const choose = (action: () => void) => { action(); if (menu.current) menu.current.open = false }
  const modes = commands.filter(command => command.category === 'options' && command.source === 'builtin')
  const skills = commands.filter(command => command.source === 'skill')
  return <>
    <details ref={menu} className="relative shrink-0">
      <summary aria-label="添加文件、模式、专家、技能或连接器" className={`flex h-10 w-10 cursor-pointer list-none items-center justify-center rounded-xl border border-dark-border text-dark-text-secondary hover:text-accent-blue ${disabled ? 'pointer-events-none opacity-50' : ''}`}><Plus size={18} /></summary>
      <div className="absolute bottom-full left-0 z-30 mb-2 w-72 rounded-xl border border-dark-border bg-dark-card p-2 shadow-xl">
        <button type="button" disabled={disabled} onClick={() => choose(onFiles)} className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-dark-card-hover">添加文件</button>
        <details><summary className="cursor-pointer px-3 py-2 text-sm">模式</summary><div className="max-h-40 overflow-y-auto pl-3">
          {modes.length ? modes.map(command => <button type="button" key={command.name} onClick={() => choose(() => onCommand(command))} className="block w-full px-3 py-2 text-left text-xs hover:bg-dark-card-hover">/{command.name} · {command.description}</button>) : <p className="px-3 py-2 text-xs text-dark-text-secondary">运行环境未提供模式选项</p>}
        </div></details>
        <details><summary className="cursor-pointer px-3 py-2 text-sm">专家</summary><div className="max-h-40 overflow-y-auto pl-3">
          {agents.length ? agents.map(agent => <button type="button" key={agent.id} onClick={() => choose(() => onExpert(agent.id))} className="block w-full px-3 py-2 text-left text-xs hover:bg-dark-card-hover">{agent.identity?.name || agent.name || agent.id}</button>) : <p className="px-3 py-2 text-xs text-dark-text-secondary">暂无可用专家</p>}
        </div></details>
        <details><summary className="cursor-pointer px-3 py-2 text-sm">技能</summary><div className="max-h-40 overflow-y-auto pl-3">
          {skills.length ? skills.map(command => <button type="button" key={command.name} onClick={() => choose(() => onCommand(command))} className="block w-full px-3 py-2 text-left text-xs hover:bg-dark-card-hover">{command.skillName || command.name}</button>) : <p className="px-3 py-2 text-xs text-dark-text-secondary">暂无已启用技能</p>}
        </div></details>
        <details><summary className="cursor-pointer px-3 py-2 text-sm">连接器</summary><p className="px-3 py-2 text-xs text-dark-text-secondary">使用已连接业务账号的资料与部门功能。</p><Link to="/settings/business-link" className="block px-3 py-2 text-xs text-accent-blue">业务账号连接</Link></details>
      </div>
    </details>
    <select aria-label="选择对话模型" title={modelError || defaultModel || '系统默认模型'} disabled={disabled || !models.length} value={model} onChange={event => onModel(event.target.value)} className="h-10 max-w-44 rounded-xl border border-dark-border bg-dark-card px-2 text-xs text-dark-text outline-none disabled:opacity-50">
      <option value="">{modelError ? '模型暂不可用' : '系统默认模型'}</option>
      {models.map(choice => <option value={choice.id} key={choice.id}>{choice.name} · {choice.provider}</option>)}
    </select>
  </>
}
