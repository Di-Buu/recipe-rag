/**
 * 用户偏好相关常量
 *
 * 统一管理 Onboarding / PreferenceView / FilterPanel 共用的选项数据，
 * 避免多处重复定义导致不一致。
 */

/** 常见过敏/禁忌食材 */
export const COMMON_ALLERGENS = [
  '花生', '虾', '蟹', '牛奶', '鸡蛋', '大豆',
  '小麦', '坚果', '芒果', '贝类', '芝麻', '鱼',
]

/** 营养目标选项（顺序固定） */
export const NUTRITION_OPTIONS = ['低脂', '高蛋白', '低卡', '高碳水']

/** 难度选项（与后端 DIFFICULTY_MAP 对应：0-简单 1-一般 2-较难 3-困难） */
export const DIFFICULTY_OPTIONS = [
  { value: null, label: '不限' },
  { value: 0, label: '简单' },
  { value: 1, label: '一般' },
  { value: 2, label: '较难' },
  { value: 3, label: '困难' },
]

/** 耗时上限选项 */
export const COSTTIME_OPTIONS = [
  { value: null, label: '不限' },
  { value: 10, label: '≤10分钟' },
  { value: 30, label: '≤30分钟' },
  { value: 60, label: '≤1小时' },
  { value: 120, label: '≤2小时' },
]

/** 筛选面板常用排除食材 */
export const COMMON_EXCLUDES = [
  '花生', '虾', '蟹', '牛奶', '鸡蛋', '大豆',
  '小麦', '坚果', '芒果', '辣椒',
]

/** 筛选面板常用包含食材 */
export const COMMON_INCLUDES = [
  '鸡肉', '猪肉', '牛肉', '鸡蛋', '豆腐',
  '土豆', '番茄', '白菜', '米饭', '面条',
]
