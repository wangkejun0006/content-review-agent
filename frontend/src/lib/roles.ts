import type { Role } from '../types'

export const roleMeta: Record<Role, { label: string; short: string; tone: string }> = {
  admin: {
    label: '系统管理员',
    short: '配置系统、管理资产与永久删除',
    tone: 'bg-blue-100 text-blue-800',
  },
  editor: {
    label: '内容运营',
    short: '维护资料、创建任务和录入数据',
    tone: 'bg-violet-100 text-violet-800',
  },
  reviewer: {
    label: '审核人员',
    short: '激活知识版本并审核最终内容',
    tone: 'bg-emerald-100 text-emerald-800',
  },
}

export const permissionRows = [
  { capability: '用户与角色管理', admin: '可以', editor: '不可以', reviewer: '不可以' },
  { capability: '产品与平台资料', admin: '编辑、归档、永久删除', editor: '编辑、归档与恢复', reviewer: '查看' },
  { capability: '知识版本激活', admin: '可以', editor: '不可以', reviewer: '可以' },
  { capability: 'Brief 与 Run', admin: '创建、编辑与清理', editor: '创建、编辑与归档', reviewer: '查看' },
  { capability: '候选内容审核', admin: '可以', editor: '查看', reviewer: '可以' },
  { capability: '发布与指标录入', admin: '可以', editor: '可以', reviewer: '查看' },
  { capability: '模型服务设置', admin: '可以', editor: '查看', reviewer: '查看' },
  { capability: '审计记录查看与导出', admin: '可以', editor: '不可以', reviewer: '不可以' },
]
