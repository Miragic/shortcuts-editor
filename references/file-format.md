# `.shortcut` 文件格式

读懂一个快捷指令，只需要理解三件事：**文件形态**、**动作结构**、**变量怎么被引用**。

---

## 1. 两种文件形态

| 形态 | 识别方式 | 能否直接编辑 |
|---|---|---|
| **明文 plist** | 前 4 字节是 `<?xm`（XML）或 `bplist`（二进制） | ✅ 直接改 |
| **AEA1 签名归档** | 前 4 字节是 `AEA1` | ❌ 先解密 |

判断与解包都用：

```bash
python3 scripts/shortcuts_tool.py inspect 文件.shortcut     # 会直接告诉你类型
python3 scripts/shortcuts_tool.py unpack  文件.shortcut -o wf.plist
```

大部分从 iPhone 导出、或从网上分享来的 `.shortcut` 是**已签名**的 AEA1 归档；而各种生成工具吐出来的是**明文 plist**。

---

## 2. 根结构

明文 plist 的根是个 dict，常用键：

| 键 | 含义 |
|---|---|
| `WFWorkflowActions` | 动作数组（核心） |
| `WFWorkflowName` | 工作流名称。**签名后会被剥离**，导入时的名字取自文件名 |
| `WFWorkflowIcon` | 图标（渐变底色 + 图形编号） |
| `WFWorkflowImportQuestions` | 导入时向用户提问的配置 |
| `WFWorkflowInputContentItemClasses` | 接受哪些类型的输入 |
| `WFQuickActionSurfaces` | 可用的快捷入口 |

单个动作的结构：

```xml
<dict>
  <key>WFWorkflowActionIdentifier</key>
  <string>is.workflow.actions.gettext</string>
  <key>WFWorkflowActionParameters</key>
  <dict>
    <key>UUID</key>
    <string>10000000-0000-0000-0000-000000000003</string>
    <!-- 其余参数 -->
  </dict>
</dict>
```

- `WFWorkflowActionIdentifier` 是动作类型。系统动作用 `is.workflow.actions.*`；App 提供的动作（App Intents）用反向域名，如 `com.apple.Numbers.TNiOSAddValuesToFormIntent`。
- `UUID` **只有需要被其它动作引用的动作才带**，且必须是**大写**的标准 UUID 字符串。不需要被引用的动作没有这个键。

---

## 3. 变量是怎么被引用的（最容易搞错的地方）

快捷指令里没有"变量名字符串"这种东西。引用是在**文本/参数内部**用占位符 + 附件描述表实现的：

```json
{
  "Value": {
    "string": "记录：￼ ｜ 金额 ￼",
    "attachmentsByRange": {
      "{4, 1}": { "Type": "ActionOutput", "OutputUUID": "…001", "OutputName": "Provided Input" },
      "{10, 1}": { "Type": "Variable", "WFVariableName": "分类" }
    },
    "WFSerializationType": "WFTextTokenString"
  },
  "WFSerializationType": "WFTextTokenAttachment"
}
```

要点：

- `string` 里的 `￼` 是 **U+FFFC（OBJECT REPLACEMENT CHARACTER）**，每个占位一个变量。
- `attachmentsByRange` 的键 `{pos,len}` 必须**精确指向**某个 U+FFFC 的起始位置。
- **`pos` 按 UTF-16 码元计数。** 中文、中文标点、emoji 都可能占 1 个以上码元，数错一位变量就废——这是排名第一的翻车点。改完 plist **必跑**：
  ```bash
  python3 scripts/validate_attachments.py wf.plist
  ```
- 键的写法 `{0,1}` 与 `{0, 1}` **都合法**（系统序列化时通常带空格，手写时常不带）。

### `Type` 的取值

| Type | 含义 | 关键字段 |
|---|---|---|
| `ActionOutput` | 引用**另一个动作的输出** | `OutputUUID`（+ `OutputName`，可读用） |
| `Variable` | 引用**已 setvariable 的变量** | `WFVariableName` |
| `CurrentDate` | 当前日期，**运行时**渲染成文本 | 无 |
| `Ask` | 引用输入的询问提示 | — |
| `ExtensionInput` | 引用快捷指令的输入 | — |

`CurrentDate` 尤其值得记：它不需要任何动作，直接内嵌在文本字段里就能得到当前日期文本。

```json
{ "string": "￼", "attachmentsByRange": { "{0, 1}": { "Type": "CurrentDate" } },
  "WFSerializationType": "WFTextTokenString" }
```

另外，纯字符串数组/字典这类**非文本**参数，用 `WFSerializationType: WFArrayParameterState` 包一层即可，不走占位符机制。

---

## 4. 控制流

控制流不是嵌套结构，而是**扁平的标记序列**——靠 `WFControlFlowMode` 表达层次：

| `WFControlFlowMode` | 含义 |
|---|---|
| `0` | 块开始（菜单本身 / 重复 / 如果） |
| `1` | 分支开始（菜单的一项 case；条件动作的「否则」） |
| `2` | 块结束 |

- 同一个块的所有分支（以及开始/结束标记）共享一个 **`GroupingIdentifier`**。这是定位某个块的唯一可靠依据。
- 菜单分支带 `WFMenuItemTitle`；**条件动作的第二个分支不带标题**（语义是「否则」）。
- 菜单的全部选项列在开始标记的 `WFMenuItems` 里。

**往分支里插动作**：必须同时按 `GroupingIdentifier`（哪个块）+ `WFMenuItemTitle`（哪个分支）定位，再插到该分支的末尾（下一个 `WFControlFlowMode` 出现之前）。只按"动作名字"去找会插错分支——多个分支里常有同名动作。

`shortcuts_tool.py inspect` 会把这段结构渲染成缩进树，改之前先看一眼：

```
▾ 选择菜单   菜单[2]: 📤支出、📥收入
  ├ 「📤支出」
    · 设置变量   变量=金额
  ├ 「📥收入」
    · 设置变量   变量=金额
└ 结束
```

---

## 5. 可靠传参的三条铁律

1. **下游动作必须显式写 `WFInput`。** 格式化、编码、打开 URL 这类动作，不要指望它自动接住上一个动作的输出——隐式串联在运行时经常拿到空值。显式写：
   ```json
   { "Value": { "OutputUUID": "…", "Type": "ActionOutput", "OutputName": "…" },
     "WFSerializationType": "WFTextTokenAttachment" }
   ```
   典型症状：`openurl` 报「未指定 URL」、某列写空。

2. **不要跨动作传 Date 对象。** 无论是 `ActionOutput` 直连还是 `setvariable` 变量桥接，Date 在真机上都可能变空（表现为目标字段空、其它字段正常）。其它类型（字符串/数组/字典）的变量桥接是可靠的，**唯独 Date 不行**。要日期就用 `CurrentDate` token。

3. **菜单取值要落地成变量。** 在菜单的每个 case 里放一个 `setvariable` 存固定文本，后续引用这个变量，而不是直接引用菜单输出。

---

## 6. 常用参数键速查

| 键 | 出现在 | 含义 |
|---|---|---|
| `WFTextActionText` | `gettext` / `alert` / `showresult` | 文本内容（字符串或 token） |
| `WFMenuItems` | `choosefrommenu` 开始标记 | 菜单选项数组 |
| `WFMenuItemTitle` | `choosefrommenu` 分支标记 | 该分支的标题 |
| `WFMenuPrompt` | `choosefrommenu` | 菜单顶部的提示语（token） |
| `WFRequestTextInputDefault` | `ask` | 输入框的默认值 |
| `WFAskActionPrompt` | `ask` | 输入框的提示语 |
| `WFDictionaryKey` | `getvalueforkey` | 要取哪个键 |
| `WFGetDictionaryValueType` | `getvalueforkey` | `Value` / `All Keys` / `All Values` |
| `WFVariableName` | `setvariable` / `getvariable` | 变量名 |
| `WFDateActionMode` | `date` | `Current Date` / `Specified Date` |
| `WFDateFormat` | `format.date` | 自定义格式串 |
| `WFFile` / `WFFilePath` | 文件类动作 | 目标文件（书签 / 路径） |
| `values` | App Intents（如 Numbers 表单） | **位置敏感**的字段数组，顺序即列序 |
| `UUID` | 任意动作 | 供其它动作引用 |

> `values` 这类 App Intent 参数是**按位置**填进目标 App 的表单/字段的——顺序错了不会报错，只会静默写错位。改之前先确认目标表格的列序。
