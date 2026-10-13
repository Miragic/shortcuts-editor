# 案例库：一个完整走完全流程的实例

> **记账只是一种场景。** 这个案例的价值在于它**完整示范了每一步怎么读、怎么改、怎么验**——同样的手法适用于任何快捷指令。

这个案例源自一个真实在用、迭代了 13 个版本的记账系统。下面每一步都标注了它在通用工作流里的位置。

---

## 0. 先读现状

拿到任何快捷指令，第一步永远是读：

```bash
python3 scripts/shortcuts_tool.py inspect 记账.shortcut
```

输出（节选）：

```
文件   : 记账.shortcut
类型   : 明文 plist（未签名）
工作流名: '记账'
动作数 : 21

动作序列:
· 要求输入   [10000000]
▾ 选择菜单   菜单[6]: 餐饮、交通、购物、娱乐…  提示='选个分类'
  ├ 「餐饮」
    · 设定变量   变量=分类
  ├ 「交通」
    · 设定变量   变量=分类
  ...
└ 结束
· 要求输入   [10000000]
· 当前日期   模式=Current Date   [10000000]
· 格式化日期   格式=yyyy-MM-dd HH:mm   [10000000]
· 文本   [10000000]
· 添加提醒事项
· 显示结果

设定过的变量: 分类
占位符检查: 4 个文本节点，全部对应正确 ✓
```

一眼就看出结构：**输入金额 → 选分类（落地成变量）→ 输入备注 → 拼日期 → 落表**。这就是后面所有改动的基线。

---

## 1. 配方 A：最简版（写入「提醒事项」）

**适用**：金额 + 一级分类 + 备注 + 时间，落到系统提醒事项，零依赖。
**动作数**：约 20。

动作顺序：

1. **Ask（Number）** —— 提示「这笔花了多少钱？」→ UUID `…001`
2. **Choose from Menu「选个分类」** —— `WFMenuItems` = 餐饮 / 交通 / 购物 / 娱乐 / 居住 / 其他
   - 开始：`WFControlFlowMode = 0`
   - 每个 case：`WFControlFlowMode = 1` + `WFMenuItemTitle = "餐饮"`，其后**紧跟一个 Set Variable「分类」= 固定文本**
     —— 关键：**用变量存菜单值，别直接引用菜单输出**（见 `pitfalls.md` A4）
   - 结束：`WFControlFlowMode = 2`
   - 全部 case 共用一个 `GroupingIdentifier`
3. **Ask（Text）** —— 提示「备注（没有就点完成）」→ UUID `…002`
4. **Current Date** —— `WFDateActionMode = "Current Date"` → UUID `…003`
5. **Format Date** —— `WFDateFormatStyle = "Custom"` + `WFDateFormat = "yyyy-MM-dd HH:mm"`，`WFDate` **显式**指向 `…003` → UUID `…004`
6. **Text（组装记录）** —— 内容 `📒 ￼ ｜ ￼ ¥￼ ｜ 备注：￼`
   - `{2,1}` = 格式化日期（`…004`）
   - `{6,1}` = 变量「分类」
   - `{9,1}` = 金额（`…001`）
   - `{16,1}` = 备注（`…002`）
   → UUID `…005`
7. **Add New Reminder** —— 标题 `记账：¥￼ ￼`（`{4,1}` = 金额，`{6,1}` = 变量「分类」）；备注 = `…005` 的输出
   **省略 `WFCalendarItemCalendar`**（避免非英文系统列表名不匹配，见 `pitfalls.md` F1）
8. **Show Result** —— `✅ 已记账：¥￼（￼）`

> **想更省事**：把第 6 步的日期引用换成 `{"Type": "CurrentDate"}` token，就能省掉第 4、5 两个动作——代价是格式随系统（见 `pitfalls.md` B1）。

---

## 2. 配方 B：完整版（写入 Numbers + 二级分类）

**适用**：要落表、要统计，分类有二级（如 餐饮 → 外卖 / 堂食）。
**动作数**：约 48。

### 2.1 先定好表格列序

```
日期 | 收支 | 分类 | 二级分类 | 金额 | 账户 | 备注
```

> ⚠️ 表单 `values` 是**位置敏感**的，顺序即列序。二级分类列必须夹在「分类」和「金额」之间，否则整行**静默错位**（见 `pitfalls.md` C4）。

### 2.2 动作顺序

1. **Ask（Number）** 金额
2. **Choose from Menu「收支」** 支出 / 📥收入（`WFControlFlowMode` 0/1/2，同一 `GroupingIdentifier`）
   - **支出 case 内：**
     - **Dictionary**：`WFItems` 为「一级分类 → 二级分类数组」。
       每条 `WFItemType = 2`，`WFKey` = 一级分类名，
       `WFValue = {"Value": ["外卖","堂食",…], "WFSerializationType": "WFArrayParameterState"}`
       （**纯字符串数组**，不是 `WFDictionaryFieldValueItems`——见 `pitfalls.md` C3）
     - **List** 一级分类（来自字典 keys）→ **Choose from List** → **Set Variable「分类」**
     - **Get Dictionary Value**（`is.workflow.actions.getvalueforkey`）：
       `WFInput` = 字典输出，`WFDictionaryKey` = 引用变量「分类」的 token，`WFGetDictionaryValueType = "Value"`
       → **Set Variable「二级列表」**
     - **Choose from List**（`WFInput` = 变量「二级列表」）→ **Set Variable「二级分类」**
   - **收入 case 内：** **Set Variable「二级分类」= "无"**（占位，防止后续引用为空）
     - ⚠️ 这个占位动作必须定位在**收入 case 内**：按 `GroupingIdentifier` + `WFMenuItemTitle` 定位。不能只找"设置变量 分类"——支出分支里也有同名来源，会插错（见 `pitfalls.md` C1）
3. **Choose from List / Menu** 选账户
4. **Ask（Text）** 备注
5. **Add Row to Numbers Form**（`com.apple.Numbers.TNiOSAddValuesToFormIntent`）
   - `formName`、`spreadsheet`（fileLocation，`relativeSubpath` 形如 `com~apple~Numbers/Documents/你的账本.numbers`）
   - `values` = 按位置排列的字段（**位置即列序**）：日期 / 收支 / 分类 / 二级分类 / 金额 / 账户 / 备注
   - 日期字段直接放 `{"Type": "CurrentDate"}` token

### 2.3 一次失败的设计决策（值得记）

早期用「嵌套 `choosefrommenu` + 每个 case 内 `choosefromlist`」做二级分类，**iOS 上二级选择器根本不弹**。改成「字典 + `getvalueforkey`」后稳定。

👉 通用结论：**需要"二级联动选择"时，不要嵌套选择器，用字典 + 取值**（见 `pitfalls.md` C2）。

---

## 3. 配方 C：再接一个桌面小组件

当需求是"记完账，桌面小组件立刻显示本月收支"，在配方 B 后面再加两步：**写一份 CSV** + **调 Scriptable 刷新**。

### 3.1 为什么要额外写 CSV

Numbers 文件是二进制、且常被 App 占用，脚本读起来麻烦。另写一份纯文本 CSV 给小组件直读，是最省事的做法。

```
日期,收支,分类,二级分类,金额,账户,备注
```

### 3.2 写 CSV 的三种写法与实测结论

| 写法 | 结果 |
|---|---|
| **字符串路径**（`WFFilePath = "Scriptable/某文件.csv"`，带不带前导 `/` 都一样） | ❌ **静默失败**。默认根是 `iCloud Drive/Shortcuts` 容器，找不到父目录就失败，**且完成提示照弹** |
| **文件书签**（用户在编辑器里用文件选择器选中目标文件夹） | ✅ **真机可用**。plist 见 `pitfalls.md` D1 |
| **调目标 App 的脚本落盘** | ✅ 可用。由脚本往自己容器里写 |

> 这也是为什么会得出「**书签才是真机可用形态**」这个结论——它是拿真实文件一格一格试出来的。

### 3.3 让小组件「立刻」刷新

| 做法 | 效果 |
|---|---|
| 只做数据下载 + 日志的同步脚本 | ❌ **不触发**小组件时间线更新 |
| **前台运行小组件脚本本身** | ✅ 唯一可靠路径 |

快捷指令侧：在末尾加一个 **Open URL**，指向

```
scriptable:///run?scriptName=<脚本名>
```

> ⚠️ 中文脚本名**必须百分号编码**（见 `pitfalls.md` F2）。

脚本侧固定写法：

```js
const w = new ListWidget();
// ... 构建内容 ...
w.refreshAfterDate = new Date(Date.now() + 60 * 1000);
Script.setWidget(w);

// 非小组件环境运行、且非 silent 模式 → 弹预览卡（兼作记账成功确认）
if (!config.runsInWidget && args.queryParameters.mode !== "silent") {
  await w.presentMedium();
}
Script.complete();
```

---

## 附录：脚本型小组件开发要点

这一节是配方 C 的下游，属于**快捷指令之外**的部分，但在实际项目里经常要一起改。

### A1 · 布局与尺寸

- `config.widgetFamily` ∈ `small`（155×155pt）/ `medium`（329×155）/ `large`（329×345）。widget 本身已是白底圆角，无需自画卡片。
- 宽度预算：内容宽 = 家族宽 − 左右 padding。中号可用「左栏固定宽 + 右栏 `layoutHorizontally`」；大号三卡等宽时 `tileW = (内容宽 − 2×间隙) / 3`。
- 固定尺寸用 `stack.size = new Size(w, 0)`（0 = 自适应）。
- **空态/错误态**：不要复用已渲染的 widget，独立 `new ListWidget` 返回，在 `main` 里先判错误与数据行数再分流。

### A2 · DrawContext 真实 API（名字与直觉差异很大）

参考 docs.scriptable.app/drawcontext。以下是**实际存在**的签名：

| 你可能想找 | 实际做法 |
|---|---|
| `fillRoundedRect` | **不存在** → `const p = new Path(); p.addRoundedRect(new Rect(x,y,w,h), cw, ch); ctx.addPath(p); ctx.fillPath()`。建议封装 `fillRRect(ctx,x,y,w,h,r)` 复用 |
| `beginPath` / `moveTo` / `addLineToPoint` / `closePath` | **不存在** → `const p = new Path(); p.move(new Point(x,y)); p.addLine(new Point(...)); p.closeSubpath(); ctx.addPath(p);` |
| `drawText(text, x, y, w, h)` | **不存在** → 只有 `drawText(text, pos: Point)` 或 `drawTextInRect(text, rect: Rect)`。要居中：先 `setTextAlignedCenter()`，再 `drawTextInRect` 一个以中心为轴、宽 = 2×半径的 rect |
| 描边路径 | `ctx.addPath(p); ctx.strokePath()`（配合 `setStrokeColor` + `setLineWidth`） |

其它：
- 字体 `ctx.setFont(Font.mediumSystemFont(size))`；文字色 `ctx.setTextColor(Color)`；填充椭圆 `ctx.fillEllipse(rect)`。
- **抗锯齿**：`ctx.size = new Size(pt * s, pt * s)`（s = 2 或 3），所有坐标与字号 ×s；`addImage` 后设 `img.imageSize = new Size(pt, pt)` 还原逻辑尺寸。

### A3 · 画环形图

顺序：
1. `fillEllipse` 画整圈轨道底色
2. 逐段用 `Path` 画扇形（从 −π/2 起顺时针）
   ⚠️ **段间留缝会吃掉小占比段**——某个段占比 < 5% 时，缝要压到 1° 以内否则看不见
3. 中心 `fillEllipse`（用卡片底色）挖洞
4. 中心 `drawTextInRect` 写两行（上小下大）

### A4 · 文件访问边界

脚本/小组件**只能读自己 App 的容器**：

```
iCloud~dk~simonbs~Scriptable/Documents      ← FileManager.iCloud().documentsDirectory()
```

它与 iCloud Drive（`com~apple~CloudDocs`）是**两个互相隔离的区**，互不可达，Scriptable 也没有反向读 iCloud Drive 的 API。

所以要「快捷指令写 → 小组件读」，只有两条路：
1. 快捷指令用**文件书签**把数据写到该容器内；
2. 快捷指令用 URL scheme 调脚本，由脚本自己落盘。

---

## 这个案例的通用收获

| 你遇到的 | 通用手法 |
|---|---|
| 不知道某个捷径做了什么 | `inspect` 看动作树 |
| 某个字段总是空 | 查是不是 Date 跨动作传递（`pitfalls.md` B1） |
| 提示成功但没写进去 | 查默认根目录与书签（`pitfalls.md` D1） |
| 想加二级联动选择 | 别嵌套选择器，用字典 + 取值（`pitfalls.md` C2） |
| 改完要交回可用文件 | 校验 → 打包 → 签名（`signing.md`） |
