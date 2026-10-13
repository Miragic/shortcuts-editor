---
name: shortcuts-editor
slug: shortcuts-editor
displayName: 快捷指令读改
version: 2.0.0
summary: 读得懂、改得动、签得出的 Apple 快捷指令工具箱 —— 解析 .shortcut（含已签名归档）、定位变量错位、手术式改造、重新签名。含 2 个可直接运行的脚本与真机踩坑清单。
description: 读取、理解、编辑、修复、重新签名 Apple「快捷指令」(.shortcut 文件)。支持已签名的 AEA1 归档自动解密、动作序列与变量摘要、占位符错位校验、plist 往返打包与重签名。当用户要查看某个快捷指令做了什么、修改已有捷径、修复捷径里变量/日期/分类输出空值、解决 .shortcut 打不开、或需要给改动后的快捷指令重新签名时使用。
description_en: Read, understand, edit, fix, and re-sign existing Apple Shortcuts (.shortcut files). Transparently handles AEA1 signed archives, summarizes the action graph and variables, validates variable placeholder offsets, and round-trips plists through unpack/pack and re-signing. Use when inspecting what a shortcut does, modifying an existing shortcut, fixing empty variables or dates, or producing a signed .shortcut.
tags:
  - 快捷指令
  - Shortcuts
  - iOS
  - macOS
  - 自动化
  - 效率工具
license: MIT
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# 快捷指令读改 Shortcuts Editor

**读取 → 理解 → 编辑 → 校验 → 重新签名** 已有的 Apple 快捷指令（`.shortcut`）。

本 skill 面向的是「手上已经有一个快捷指令」的场景：一个别人发来的文件、一个自己导出的备份、一个突然不好用的捷径。不是从零生成，而是**把它拆开、看懂、改对、再装回去**。

---

## 什么时候用

| 你在问 | 走哪条路 |
|---|---|
| 「这个快捷指令到底做了什么？」 | `inspect` 打印动作序列 |
| 「第 N 步不对 / 某个变量是空的 / 提示未指定 URL」 | `inspect` 定位 → `unpack` 改 → `pack` → 签名 |
| 「帮我加一步 / 换分类 / 换写入目标 / 换提示语」 | `unpack` → 编辑 plist → `pack` → 签名 |
| 「我有个导出的 .shortcut，电脑上打不开、没法改」 | `unpack`（签名归档会自动解密） |
| 「改完导不进 iPhone / 提示未签名」 | `shortcuts sign` 重签 |
| 「变量错位了，不知道差在哪一位」 | `validate_attachments.py` |

**与 `shortcuts-generator` 的分工**：那个 skill 解决「从无到有」——它带 1155 个动作的字典，适合新写一个捷径。本 skill 解决「从有到改」——重点在解析、定位、最小改动、往返不变形。两者可以配合用。

---

## 前置条件

- **macOS** —— `shortcuts` 命令行只有 macOS 有，签名步骤必需。
- 系统自带：`shortcuts`、`aea`、`aa`、`openssl`（后三个随 AppleArchive / 系统提供，无需安装）。
- **Python 3** —— 两个脚本均为纯标准库，无第三方依赖。

---

## 核心工作流

### ① 读 —— 先看懂，再动手

```bash
python3 scripts/shortcuts_tool.py inspect 我的捷径.shortcut
```

输出：文件类型（明文 / AEA1 签名归档）、签名证书与有效期、工作流名、动作总数、**带缩进的动作序列**（控制流展开成树）、设定过与读取过的变量、占位符检查结果。

```bash
python3 scripts/shortcuts_tool.py inspect 我的捷径.shortcut --json   # 便于程序处理
```

> 已签名的文件会**自动解密**，不需要先手动 `aea decrypt`。

### ② 改 —— 导出成可编辑的 plist

```bash
python3 scripts/shortcuts_tool.py unpack 我的捷径.shortcut -o wf.plist
# 编辑 wf.plist（XML plist，可直接用编辑器改）
python3 scripts/shortcuts_tool.py pack  wf.plist -o 我的捷径_v2.shortcut
```

### ③ 校验 —— **跳过这步是最常见的翻车点**

```bash
python3 scripts/validate_attachments.py wf.plist
```

逐个检查每个文本节点里的 U+FFFC 占位符与 `attachmentsByRange` 是否一一对应。**差一位，变量就废**。

### ④ 签 —— 交回可用文件

```bash
shortcuts sign --mode anyone --input 我的捷径_v2.shortcut --output 我的捷径_v2_signed.shortcut
```

`--mode anyone` 无需原私钥，签出的文件可导入任意设备。

> 完整往返（解包 → 改 → 打包 → 重签 → 再读回）已实测跑通，步骤与报错对照见 `references/signing.md`。

---

## 关键规则（真会咬人的那些）

**文件格式**
- `.shortcut` 有两种形态：**明文 plist**（可任意编辑）与 **AEA1 签名归档**（前 4 字节魔数 `AEA1`）。先判断形态再动手。
- 编辑签名文件前必须**解密整个文件**（不是 payload 之后的字节）；公钥要从**该文件自身**的 `SigningCertificateChain[0]` 导出，旧公钥不可复用。

**变量引用（排名第一的翻车点）**
- 文本里的变量是占位符 `￼`（U+FFFC），由 `attachmentsByRange` 的 `{pos,len}` 指向。`pos` 按 **UTF-16 码元**计数——中文、标点、emoji 都可能占 1 个以上码元。
- 键可能是 `{0,1}` 也可能是 `{0, 1}`（系统序列化带空格），**两种都合法**。
- 下游动作（格式化、编码、打开 URL 等）**必须显式写 `WFInput`** 指向上游 UUID，不要依赖动作顺序隐式串联——隐式串联会在运行时拿到空值。

**数据传递**
- 跨动作传 **Date 对象**在真机上不可靠（无论直连还是变量桥接），表现为目标字段全空、其它字段正常。要当前日期就内嵌 `{"Type": "CurrentDate"}` token。
- 菜单选中值用 case 内 `setvariable` 存成固定文本，**不要直接引用菜单输出**。

**控制流**
- 控制流由 `WFControlFlowMode` 标记：`0` = 块开始、`1` = 分支、`2` = 块结束；同一块的多个分支共享一个 `GroupingIdentifier`。
- 往某个分支里插动作，必须按 `GroupingIdentifier` + `WFMenuItemTitle` **精确定位**，否则会插错分支。
- 条件动作的第二个分支没有标题（语义是「否则」）。

**写文件（最容易「假装成功」的地方）**
- 用**字符串路径**写 iCloud Drive 会**静默失败**——完成提示照弹，文件没内容。根因：文件类动作的默认根目录是 `iCloud Drive/Shortcuts` 容器，不是 iCloud Drive 根。
- 真机可用的形态是**文件书签**：`WFFile` 指向用户用文件选择器选定的文件夹 ＋ `WFFilePath` 只写纯文件名。书签含设备绑定标识，**程序无法伪造**，只能让用户在 App 里选一次，或复制一份已含书签的导出版当底版。

**签名**
- `shortcuts sign` 每次生成**全新证书**，并**剥掉 `WFWorkflowName`**——导入后的名称取自文件名。
- 签名需联网，**在沙箱内执行会 SSL 失败**。
- 终端可能打印一串 `Unrecognized attribute string flag ...`——这是该命令在部分环境下的**无害告警**，产物仍然有效（用 `inspect` 回读即可确认）。

---

## 故障排查

| 症状 | 大概率根因 | 怎么修 |
|---|---|---|
| 文件打不开 / 编辑器里是乱码 | 是 AEA1 签名归档，不是明文 plist | `shortcuts_tool.py unpack` 自动解密 |
| 导入后提示「未指定 URL」 | `openurl` 的 URL 靠隐式串联拿了空值 | 给该动作补显式 `WFInput` |
| 某个字段写进去全是空（其它正常） | 该字段用 Date 对象跨动作传递，或靠隐式串联 | 改用 `CurrentDate` token ＋ 显式 `WFInput` |
| 变量引用的值不对／整体错位 | `{pos,len}` 偏移差了一位 | 跑 `validate_attachments.py` 定位 |
| 菜单分支里的动作跑错分支 | 插入位置只按动作名找，没按分支定位 | 按 `GroupingIdentifier` + `WFMenuItemTitle` 定位 |
| 写文件提示成功但文件里没内容 | 字符串路径写到了 Shortcuts 容器 | 改用文件书签形态 |
| 嵌套选择器（选择器里再弹选择器）不响应 | 部分嵌套结构在 iOS 上不触发 | 改成「字典 + 取值」两步走 |
| `shortcuts sign` 报 SSL / 连接失败 | 在沙箱内执行 | 到沙箱外重跑 |
| 签名后有 `Unrecognized attribute string flag` 报错 | 该命令在部分环境的无害告警 | 忽略，用 `inspect` 回读确认产物有效 |
| 改完导入没变化 | 导的是旧的签名文件 | 确认导的是 `*_signed.shortcut` |

---

## 目录

```
shortcuts-editor/
├── SKILL.md                        ← 本文件：定位、工作流、规则、故障排查
├── references/
│   ├── file-format.md              ← .shortcut 内部结构：动作、UUID、变量引用、控制流
│   ├── signing.md                  ← 签名与解密往返（完整命令 + 报错对照）
│   ├── pitfalls.md                 ← 踩坑清单（按主题编号）
│   └── examples.md                 ← 案例库：一个完整走完全流程的实例
├── scripts/
│   ├── shortcuts_tool.py           ← inspect / unpack / pack 三合一
│   └── validate_attachments.py     ← 占位符校验器（改完必跑）
└── assets/                         ← 出厂不含模板；放你自己的导出件（见下）
```

**关于 `assets/`**：出厂**不含任何快捷指令模板**（只有一个说明文件）。快捷指令导出件往往含设备绑定的文件书签，不适合随 skill 分发——请把你**自己导出的** `.shortcut` 放进来作为起点。没有模板也能用：`inspect` 任何现成文件都是好的起点。

---

## 案例库

`references/examples.md` 收录了一个完整实例——**记账快捷指令**（输入金额 → 选分类 → 落表 → 接桌面小组件）。它覆盖了这套流程里几乎所有难点：多级菜单、字典取值、静默失败的写文件、签名往返，以及「快捷指令写 → 小组件读」的跨容器问题。

> 记账只是**一个使用场景**。案例的价值在于它示范了**每一步怎么读、怎么改、怎么验**——同样的手法适用于任何快捷指令。
