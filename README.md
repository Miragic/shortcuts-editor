# Shortcuts Editor · 快捷指令读改

**读懂、改对、修好 Apple 快捷指令** —— 一个面向 `.shortcut` 文件的读取 / 编辑 / 校验 / 重签名工具包。

![License](https://img.shields.io/badge/license-MIT-6C69DC)
![Python](https://img.shields.io/badge/python-3.8%2B-3776AB)
![Signing](https://img.shields.io/badge/signing-macOS%20only-lightgrey)

> 别人发来的捷径看不懂？自己导出的备份想改一下？某把老捷径突然不好用了？
> 这个包帮你把它拆开看清楚、改对、再签回去 —— 交给你的文件可以直接导入 iPhone。

---

## 目录

- [为什么需要它](#为什么需要它)
- [能做什么](#能做什么)
- [快速开始](#快速开始)
  - [路线 A · 装成 AI 技能（推荐）](#路线-a--装成-ai-技能推荐)
  - [路线 B · 直接用脚本](#路线-b--直接用脚本)
- [命令行参考](#命令行参考)
- [前置条件](#前置条件)
- [目录结构](#目录结构)
- [它是怎么工作的](#它是怎么工作的)
- [可靠性](#可靠性)
- [常见问题](#常见问题)
- [与同类项目的关系](#与同类项目的关系)
- [许可证](#许可证)

---

## 为什么需要它

`.shortcut` 文件本质是一个 plist。想改它，你得先面对这几个问题：

- **它是二进制签名包** —— 从 iPhone 导出的捷径大多带 AEA1 签名，直接打开是乱码，得先解密
- **变量引用是隐式的** —— 文本里的变量存成 `U+FFFC` 占位符 + 一张 `{位置, 长度}` 的 range 表，肉眼看不见。**差一位就整条捷径崩**，而且往往不报错，只是"某一列写进去全是空"
- **改完还得签回去** —— 未签名的文件在 iPhone 上导入会被拒

这套东西自己踩一遍要花不少时间。这个包把它做成了可复用的工具和文档。

---

## 能做什么

| 场景 | 用什么 |
|---|---|
| 想知道一个快捷指令到底做了什么 | `inspect` —— 把动作序列、变量、控制流列成树 |
| 要改里面的内容（加步骤、换分类、换写入目标） | `unpack` → 编辑 plist → `pack` |
| 改完不确定变量引用有没有错位 | `validate_attachments.py` —— 专抓"差一位" |
| 改完要能装回 iPhone | `shortcuts sign` —— 重签名流程见 `references/signing.md` |

**已签名的文件会自动解密**，不需要你手动折腾证书链。

---

## 快速开始

### 路线 A · 装成 AI 技能（推荐）

这是它设计时的形态 —— 给 AI 助手（WorkBuddy / CodeBuddy 等支持 Skill 的环境）用的技能包。装上之后直接用自然语言说话：

```
帮我看看这个快捷指令都做了些什么
/Users/me/Downloads/某捷径.shortcut
```

```
我这个捷径里，日期那一列写进去总是空的，帮我找找问题在哪
```

```
帮我在这个捷径里加一步：记完之后顺便发个通知
```

```
这个捷径我改完了，帮我签名，我要装到手机上
```

安装方式：把整个目录复制到你的 skills 目录即可。

```bash
# WorkBuddy
cp -r shortcuts-editor ~/.workbuddy/skills/

# CodeBuddy
cp -r shortcuts-editor ~/.codebuddy/skills/
```

### 路线 B · 直接用脚本

不需要 AI，两个纯标准库的 Python 脚本就能用。

```bash
# 1. 读懂一个捷径（自动识别明文 / 已签名）
python3 scripts/shortcuts_tool.py inspect ~/Downloads/我的捷径.shortcut

# 2. 解开成可编辑的 XML plist
python3 scripts/shortcuts_tool.py unpack ~/Downloads/我的捷径.shortcut -o wf.plist

# 3. 编辑 wf.plist —— 文本编辑器、Python、plistlib 都行
#    （结构说明见 references/file-format.md）

# 4. 校验变量占位符 —— 改完必跑，这一步能挡掉大多数崩溃
python3 scripts/validate_attachments.py wf.plist

# 5. 打包回 .shortcut
python3 scripts/shortcuts_tool.py pack wf.plist -o 我的捷径_v2.shortcut -n "我的捷径"

# 6. 重新签名（需 macOS）
shortcuts sign --mode anyone --input 我的捷径_v2.shortcut --output 我的捷径_v2_signed.shortcut
```

`inspect` 的真实输出长这样：

```
文件   : ~/Downloads/我的捷径.shortcut
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
读取的变量  : （无）

占位符检查: 4 个文本节点，全部对应正确 ✓
```

控制流（菜单 / 条件判断）会自动展开成缩进树，`[10000000]` 是动作 UUID 的前缀。

---

## 命令行参考

### `shortcuts_tool.py inspect <file> [--json]`

读取并打印动作序列、变量统计、占位符检查结果。自动识别明文与 AEA1 签名（签名文件会打印证书与有效期）。`--json` 输出结构化结果，便于交给其它程序处理。

退出码：`0` 成功，`1` 失败。

### `shortcuts_tool.py unpack <file> -o <output.plist>`

把签名或明文 `.shortcut` 导出为可编辑的 XML plist。内含完整 AEA1 解密流程（提取证书链 → 取公钥 → `aea decrypt` → `aa extract`）。

### `shortcuts_tool.py pack <plist> -o <output.shortcut> [-n NAME]`

把编辑后的 plist 打包回 `.shortcut`。`-n` 可顺带设置 `WFWorkflowName`。

### `validate_attachments.py <plist 或 .shortcut>`

检查文本节点里的 `U+FFFC` 占位符与 `attachmentsByRange` 的 range 表是否一一对应、位置是否吻合。**这是最容易出错、又最难肉眼发现的地方**，改完 plist 一定要跑。

---

## 前置条件

| 需求 | 说明 |
|---|---|
| **Python 3** | 两个脚本都是纯标准库，**不需要 `pip install` 任何东西** |
| **macOS** | 仅**签名**这一步需要（Apple 只把 `shortcuts` / `aea` 命令放在 macOS） |
| iPhone / iPad | 用来运行快捷指令 |
| 相关 App | 看具体捷径。若它用了某个 App 的动作（如 Numbers、Scriptable），你也需要装那个 App |

> 没有 Mac 也能做大部分工作：读取、解析、编辑 plist、校验都不需要签名。只是最后"装回 iPhone"这一步需要 Mac。

---

## 目录结构

```
shortcuts-editor/
├── SKILL.md                        AI 助手读的说明书：定位、工作流、关键规则、故障排查表
├── README.md                       你正在看的这份
├── LICENSE                         MIT
├── _icon.png                       项目图标
├── references/
│   ├── file-format.md              .shortcut 内部结构：动作、UUID、变量引用、控制流
│   ├── signing.md                  签名与解密往返（完整命令 + 报错对照）
│   ├── pitfalls.md                 踩坑清单（按主题编号，症状 → 根因 → 修法）
│   └── examples.md                 案例库：一个完整走完全流程的实例
├── scripts/
│   ├── shortcuts_tool.py           inspect / unpack / pack 三合一
│   └── validate_attachments.py     变量占位符校验器（改完必跑）
└── assets/                         留空，给你放自己导出的模板
```

---

## 它是怎么工作的

```
   你的 .shortcut 文件
   （可能是 AEA1 签名的）
          │
          │  ① inspect / unpack
          ▼
   解出 plist ──────────────────────┐
   （动作数组 + 变量引用表）          │
          │                          │
          │  ② 编辑                  │  ④ validate
          ▼                          │     检查占位符
   改好的 plist ──────────────────────┘     是否错位
          │
          │  ③ pack
          ▼
   新的 .shortcut
          │
          │  ⑤ shortcuts sign --mode anyone
          ▼
   可直接导入 iPhone 的签名文件
```

关键点：**每一次改动都在导出后的 plist 副本上做，原始文件不动**。改坏了就退回原文件重来。

---

## 可靠性

这个包不是凭空写的文档，而是从一个**真实在用、迭代了 13 个版本**的快捷指令项目里提炼出来的。每条规则背后都对应一次真机上踩到的坑：

| 症状 | 真实根因 |
|---|---|
| 日期那一列写进去一直是空的 | 跨动作传递日期对象在真机上不可靠，得改用 `CurrentDate` token |
| 提示成功但文件里没内容 | 文件类动作的默认根目录不是 iCloud Drive 根，而是 App 的容器 |
| 二级分类选择器点不出来 | 嵌套菜单在真机上的表现问题，改用字典 + 取值更稳 |
| 变量引用错位（改一处崩一处） | 占位符 range 表差一位 —— 因此写出了 `validate_attachments.py` |

`references/pitfalls.md` 里按主题整理了 **20+ 条**，都能直接对号入座。

**整条链路是实测跑通过的**：拿一份 50 个动作的真实签名文件，走完
`unpack` → `pack` → 再次 `unpack`，
**两次解包的内容完全一致**（重签后证书为新签发、`WFWorkflowName` 按预期被剥离，回读正常）。

这一步验证过了，才敢说"改了不会坏"。

---

## 常见问题

**Q：一定要 Mac 吗？**
读取和编辑不需要，签名需要。签名用的是 Apple 自己的工具，只有 macOS 上才有。没有 Mac 可以让 AI 出未签名版本，导入时手动确认信任。

**Q：会不会收集我的数据？**
不会。整个包是纯本地的文档和脚本，**不联网、不上传**。你的快捷指令文件始终在你自己的设备上。

**Q：只支持记账相关的捷径吗？**
不是。**记账只是案例**。读取、解析、改造、校验、签名这套手法对任何快捷指令都适用；案例之所以选记账，是因为它把各种坑都踩了一遍，正好用来示范。

**Q：改坏了怎么办？**
改之前先留一份原始文件。所有改动都在导出后的 plist 副本上做，原始 `.shortcut` 不动 —— 实在不行就退回原文件重来。

**Q：为什么脚本里调用了 `openssl` / `aea` / `aa`？**
这是解开 AEA1 签名归档所必需的（macOS 自带）。**只在你显式指定某个文件时执行，不会扫描目录**。

---

## 与同类项目的关系

| | `shortcuts-generator` | **本项目** |
|---|---|---|
| 方向 | 从**无**到**有** | 从**有**到**改** |
| 强项 | 动作标识查询（1,155 个动作字典）、新建捷径 | 解析现成文件、定位问题、最小改动、往返重签 |
| 适合的提问 | "帮我做个捷径" | "这个捷径怎么改 / 怎么坏了" |

两者**互补**，可以同时使用。

---

## 许可证

[MIT](LICENSE) © 2026 Miragic
