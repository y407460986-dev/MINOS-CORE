# PFMEA 表格横向滚动体验优化计划

## 问题描述

在 MINOS-CORE 的 PFMEA 表格中，用户需要先将页面垂直滚动到最底部，才能使用横向滚动条进行水平滚动。这严重影响了用户体验，尤其是在编辑宽表格时。

## 问题根源

- 文件：`apps/desktop-tauri/src/components/WorkbenchTable.tsx:542`
- 表格使用固定高度的滚动容器：`max-h-[calc(100vh-330px)] min-h-[440px] overflow-auto`
- 横向滚动条位于滚动容器的底部
- 当表格行数较多时，横向滚动条不可见

## 解决方案

采用 **3 个互补方案** 的组合，提供最佳用户体验：

### 方案 1：粘性横向滚动条（主要方案）⭐

#### 实现原理
在表格容器底部添加一个独立的、始终可见的横向滚动条，与表格的实际滚动同步。

#### 技术实现
1. 创建新组件 `StickyHorizontalScrollbar.tsx`
2. 使用 `position: sticky` 固定在容器底部
3. 通过 `useEffect` 同步两个滚动条的位置

#### 代码结构
```tsx
// apps/desktop-tauri/src/components/StickyHorizontalScrollbar.tsx
export function StickyHorizontalScrollbar({ 
  targetRef, 
  className 
}: { 
  targetRef: RefObject<HTMLElement>; 
  className?: string;
}) {
  // 实现滚动同步逻辑
}
```

#### 优点
- ✅ 用户无需滚动即可访问横向滚动条
- ✅ 实现相对简单
- ✅ 不改变现有布局
- ✅ 兼容性好

#### 缺点
- ⚠️ 需要额外的 DOM 元素
- ⚠️ 需要 JavaScript 同步逻辑

---

### 方案 2：鼠标拖拽滚动（辅助方案）⭐

#### 实现原理
支持在表格内按住鼠标（或按住 Shift 键）拖拽进行横向滚动，类似 Figma 的画布拖拽。

#### 技术实现
1. 创建自定义 Hook `useDragScroll.ts`
2. 监听 `mousedown`、`mousemove`、`mouseup` 事件
3. 根据鼠标移动距离调整 `scrollLeft`
4. 添加视觉反馈（光标变化为 `grab`/`grabbing`）

#### 代码结构
```tsx
// apps/desktop-tauri/src/hooks/useDragScroll.ts
export function useDragScroll(
  ref: RefObject<HTMLElement>,
  options?: {
    requireShiftKey?: boolean;
    direction?: 'horizontal' | 'vertical' | 'both';
  }
) {
  // 实现拖拽滚动逻辑
}
```

#### 优点
- ✅ 更直观的交互方式
- ✅ 不需要滚动条也能横向移动
- ✅ 类似专业工具的体验
- ✅ 对触控板用户友好

#### 缺点
- ⚠️ 可能与现有的行拖拽功能冲突（需要用 Shift 键区分）
- ⚠️ 需要用户学习新的交互方式

---

### 方案 3：键盘快捷键（增强方案）⭐

#### 实现原理
支持使用键盘方向键进行横向滚动。

#### 技术实现
1. 监听 `keydown` 事件
2. `ArrowLeft`/`ArrowRight`：小幅度滚动（50px）
3. `Shift + ArrowLeft`/`ArrowRight`：大幅度滚动（200px）
4. `Home`/`End`：滚动到最左/最右

#### 代码结构
```tsx
// 在 WorkbenchTable.tsx 中添加
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      // 实现键盘滚动逻辑
    }
  };
  // ...
}, []);
```

#### 优点
- ✅ 提供额外的交互方式
- ✅ 对键盘用户友好
- ✅ 实现简单
- ✅ 符合用户习惯

#### 缺点
- ⚠️ 可能与表格内的输入框冲突（需要判断焦点）

---

## 实施步骤

### 阶段 1：粘性横向滚动条（优先级：高）

#### 步骤 1.1：创建 StickyHorizontalScrollbar 组件
- [ ] 创建文件 `apps/desktop-tauri/src/components/StickyHorizontalScrollbar.tsx`
- [ ] 实现基础滚动条 UI
- [ ] 实现滚动同步逻辑
- [ ] 添加样式和动画

#### 步骤 1.2：集成到 WorkbenchTable
- [ ] 在 `WorkbenchTable.tsx` 中引入组件
- [ ] 创建 `scrollContainerRef` 引用
- [ ] 将 ref 传递给滚动容器和粘性滚动条
- [ ] 测试滚动同步

#### 步骤 1.3：样式优化
- [ ] 确保滚动条始终可见
- [ ] 添加阴影效果区分层次
- [ ] 适配深色模式（如果有）
- [ ] 响应式适配

#### 验证标准
- ✅ 横向滚动条始终可见在表格底部
- ✅ 两个滚动条位置完全同步
- ✅ 滚动流畅，无卡顿
- ✅ 样式与现有设计一致

---

### 阶段 2：鼠标拖拽滚动（优先级：中）

#### 步骤 2.1：创建 useDragScroll Hook
- [ ] 创建文件 `apps/desktop-tauri/src/hooks/useDragScroll.ts`
- [ ] 实现基础拖拽逻辑
- [ ] 添加 Shift 键检测（避免与行拖拽冲突）
- [ ] 添加光标样式切换

#### 步骤 2.2：集成到 WorkbenchTable
- [ ] 在 `WorkbenchTable.tsx` 中引入 Hook
- [ ] 应用到滚动容器
- [ ] 测试与现有拖拽功能的兼容性
- [ ] 添加用户提示（首次使用时）

#### 步骤 2.3：交互优化
- [ ] 添加拖拽惯性效果
- [ ] 优化拖拽灵敏度
- [ ] 添加边界检测
- [ ] 添加视觉反馈

#### 验证标准
- ✅ 按住 Shift + 鼠标拖拽可以横向滚动
- ✅ 不影响现有的行拖拽功能
- ✅ 光标样式正确切换
- ✅ 拖拽流畅自然

---

### 阶段 3：键盘快捷键（优先级：低）

#### 步骤 3.1：实现键盘滚动逻辑
- [ ] 在 `WorkbenchTable.tsx` 中添加 `useEffect`
- [ ] 监听 `keydown` 事件
- [ ] 实现方向键滚动
- [ ] 实现 Home/End 滚动

#### 步骤 3.2：焦点管理
- [ ] 检测当前焦点是否在输入框内
- [ ] 仅在表格容器获得焦点时响应快捷键
- [ ] 添加焦点指示器

#### 步骤 3.3：用户引导
- [ ] 在设置页面添加快捷键说明
- [ ] 添加工具提示
- [ ] 更新用户文档

#### 验证标准
- ✅ 方向键可以横向滚动
- ✅ Shift + 方向键大幅度滚动
- ✅ Home/End 滚动到边界
- ✅ 不影响输入框内的光标移动

---

## 技术细节

### 粘性滚动条实现要点

```tsx
// 关键代码片段
const StickyHorizontalScrollbar = ({ targetRef }: Props) => {
  const scrollbarRef = useRef<HTMLDivElement>(null);
  const [scrollWidth, setScrollWidth] = useState(0);
  const [clientWidth, setClientWidth] = useState(0);

  useEffect(() => {
    const target = targetRef.current;
    const scrollbar = scrollbarRef.current;
    if (!target || !scrollbar) return;

    // 同步滚动位置
    const syncScroll = () => {
      scrollbar.scrollLeft = target.scrollLeft;
    };

    const syncScrollFromBar = () => {
      target.scrollLeft = scrollbar.scrollLeft;
    };

    target.addEventListener('scroll', syncScroll);
    scrollbar.addEventListener('scroll', syncScrollFromBar);

    return () => {
      target.removeEventListener('scroll', syncScroll);
      scrollbar.removeEventListener('scroll', syncScrollFromBar);
    };
  }, [targetRef]);

  return (
    <div 
      ref={scrollbarRef}
      className="sticky bottom-0 z-10 overflow-x-auto overflow-y-hidden"
      style={{ height: '12px' }}
    >
      <div style={{ width: scrollWidth, height: '1px' }} />
    </div>
  );
};
```

### 拖拽滚动实现要点

```tsx
// 关键代码片段
const useDragScroll = (ref: RefObject<HTMLElement>) => {
  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    let isDragging = false;
    let startX = 0;
    let scrollLeft = 0;

    const handleMouseDown = (e: MouseEvent) => {
      if (!e.shiftKey) return; // 需要按住 Shift
      isDragging = true;
      startX = e.pageX - element.offsetLeft;
      scrollLeft = element.scrollLeft;
      element.style.cursor = 'grabbing';
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      e.preventDefault();
      const x = e.pageX - element.offsetLeft;
      const walk = (x - startX) * 2; // 滚动速度倍数
      element.scrollLeft = scrollLeft - walk;
    };

    const handleMouseUp = () => {
      isDragging = false;
      element.style.cursor = 'grab';
    };

    element.addEventListener('mousedown', handleMouseDown);
    element.addEventListener('mousemove', handleMouseMove);
    element.addEventListener('mouseup', handleMouseUp);
    element.addEventListener('mouseleave', handleMouseUp);

    return () => {
      element.removeEventListener('mousedown', handleMouseDown);
      element.removeEventListener('mousemove', handleMouseMove);
      element.removeEventListener('mouseup', handleMouseUp);
      element.removeEventListener('mouseleave', handleMouseUp);
    };
  }, [ref]);
};
```

---

## 测试计划

### 功能测试
- [ ] 粘性滚动条在所有三个表格（PFD、PFMEA、CP）中正常工作
- [ ] 滚动条同步准确无延迟
- [ ] 拖拽滚动不影响行拖拽功能
- [ ] 键盘快捷键不影响输入框编辑
- [ ] 所有交互方式可以组合使用

### 兼容性测试
- [ ] Chrome 最新版
- [ ] Firefox 最新版
- [ ] Edge 最新版
- [ ] Safari 最新版（macOS）
- [ ] 触控板滚动
- [ ] 鼠标滚轮滚动

### 性能测试
- [ ] 大数据量表格（100+ 行）滚动流畅
- [ ] 滚动同步无明显延迟
- [ ] 内存占用无明显增加
- [ ] CPU 占用正常

### 用户体验测试
- [ ] 新用户能快速发现横向滚动功能
- [ ] 交互方式直观易懂
- [ ] 视觉反馈清晰
- [ ] 无意外行为

---

## 风险与缓解

### 风险 1：与现有行拖拽功能冲突
**影响：** 高  
**概率：** 中  
**缓解措施：**
- 使用 Shift 键区分拖拽滚动和行拖拽
- 在拖拽手柄上禁用拖拽滚动
- 添加清晰的视觉反馈

### 风险 2：滚动同步性能问题
**影响：** 中  
**概率：** 低  
**缓解措施：**
- 使用 `requestAnimationFrame` 优化同步
- 添加防抖/节流
- 监控性能指标

### 风险 3：浏览器兼容性问题
**影响：** 中  
**概率：** 低  
**缓解措施：**
- 使用标准 Web API
- 添加 polyfill（如需要）
- 充分的跨浏览器测试

---

## 成功标准

### 必须达成（Must Have）
- ✅ 用户无需滚动到底部即可进行横向滚动
- ✅ 横向滚动条始终可见
- ✅ 滚动流畅无卡顿
- ✅ 不影响现有功能

### 应该达成（Should Have）
- ✅ 支持鼠标拖拽滚动
- ✅ 支持键盘快捷键
- ✅ 有清晰的视觉反馈
- ✅ 通过所有测试用例

### 可以达成（Could Have）
- ⭕ 添加滚动惯性效果
- ⭕ 添加滚动位置指示器
- ⭕ 添加用户引导动画
- ⭕ 支持自定义滚动速度

---

## 时间估算

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| 阶段 1 | 粘性横向滚动条 | 4-6 小时 |
| 阶段 2 | 鼠标拖拽滚动 | 3-4 小时 |
| 阶段 3 | 键盘快捷键 | 2-3 小时 |
| 测试 | 功能、兼容性、性能测试 | 3-4 小时 |
| 文档 | 更新用户文档和代码注释 | 1-2 小时 |
| **总计** | | **13-19 小时** |

---

## 后续优化

### 短期优化（1-2 周内）
- 收集用户反馈
- 优化滚动性能
- 修复发现的 bug
- 完善用户引导

### 中期优化（1-2 月内）
- 添加滚动位置记忆功能
- 支持自定义滚动速度
- 添加滚动位置指示器
- 优化触控板体验

### 长期优化（3+ 月）
- 考虑虚拟滚动优化大数据量
- 添加表格列宽自适应
- 支持列固定/冻结
- 添加表格视图预设

---

## 参考资料

### 类似实现
- [react-sticky-table](https://github.com/samrith-s/react-sticky-table)
- [react-window](https://github.com/bvaughn/react-window)
- [TanStack Table - Sticky Columns](https://tanstack.com/table/v8/docs/guide/column-pinning)

### 设计参考
- Figma 画布拖拽
- Google Sheets 横向滚动
- Notion 表格滚动
- Airtable 表格交互

---

## 附录

### 相关文件清单
- `apps/desktop-tauri/src/components/WorkbenchTable.tsx` - 主表格组件
- `apps/desktop-tauri/src/components/ui/table.tsx` - 基础表格组件
- `apps/desktop-tauri/src/pages/ThreeTableWorkbench.tsx` - 工作台页面

### 涉及的技术栈
- React 18
- TypeScript
- Tailwind CSS
- @tanstack/react-table
- Tauri

---

**文档版本：** v1.0  
**创建日期：** 2026-05-30  
**最后更新：** 2026-05-30  
**负责人：** Claude (AI Assistant)  
**状态：** 待审核
