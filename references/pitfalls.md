# 踩坑清单

按主题编号。每一条都是**真机上踩过**的——症状、根因、修法。

---

## A. 变量引用

**A1 · 占位符偏移一位**
- 症状：某个变量引用出来是错的，或整段文本错位。
- 根因：`attachmentsByRange` 的 `{pos,len}` 没精确指向 U+FFFC 的起始位置。
- 修法：`pos` 按 **UTF-16 码元**计数，中文/中文标点/emoji 都可能是多码元。**改完必跑** `validate_attachments.py`。
- 注意：键写 `{0,1}` 或 `{0, 1}` 都合法，别被空格吓到。

**A2 · 占位符数量与附件数量不等**
- 症状：校验脚本直接报数量不匹配；运行时变量位置串了。
- 根因：删文本时删掉了 `￼`（U+FFFC，肉眼看不见），或新增了 `￼` 但没配附件。
- 修法：在十六进制视图里检查，或用 `inspect` 看该节点的占位符计数。

**A3 · 依赖隐式串联拿值**
- 症状：报「未指定 URL」，或某字段写空。
- 根因：下游动作（格式化 / 编码 / 打开 URL 等）没有显式 `WFInput`，指望它自动接住上一个动作的输出。
- 修法：显式写 `WFInput` → `{"Value": {"OutputUUID": "...", "Type": "ActionOutput"}, "WFSerializationType": "WFTextTokenAttachment"}`。

**A4 · 菜单取值直接引用菜单输出**
- 症状：后续拿到的不是固定分类文本，行为不稳定。
- 根因：直接引用"菜单输出"而非落地成变量。
- 修法：在每个 case 内放一个 `setvariable` 存**固定文本**，后续引用该变量。

---

## B. 数据传递与日期

**B1 · 跨动作传 Date 对象变空（踩坑最多）**
- 症状：某一列/某个字段写进去**全是空**，其它字段正常。
- 根因：**Date 对象跨动作传递在真机上不可靠**——`ActionOutput` 直连、`setvariable` 变量桥接，两条路都试过，都会空。其它类型（字符串 / 数组 / 字典）的桥接是可靠的，唯独 Date。
- 修法：要当前日期就**内嵌 token**，不要建动作、不要存变量：
  ```json
  { "string": "￼", "attachmentsByRange": { "{0, 1}": { "Type": "CurrentDate" } },
    "WFSerializationType": "WFTextTokenString" }
  ```
- 代价：格式不可控（中文环境约 `2026年9月9日 15:33`）。若必须固定 `yyyy-MM-dd`，让**下游**（脚本/表格公式）做归一化，别在快捷指令里硬转。

**B2 · `date` 动作被上一个动作的输出污染**
- 症状：日期取出来不对。
- 根因：`date` 动作没写 `WFDateActionDate`，无参数时会被前一动作的文本输出顶掉。
- 修法：显式写 `WFDateActionDate: {"Type": "CurrentDate"}`。若只是要当前日期，直接用 B1 的 token 更省事。

---

## C. 控制流

**C1 · 往分支里插动作插错位置**
- 症状：动作跑到另一个分支里去了；或多分支里有同名动作时改错了地方。
- 根因：只按动作名/索引定位。
- 修法：按 **`GroupingIdentifier`（哪个块）+ `WFMenuItemTitle`（哪个分支）** 定位，插到下一个 `WFControlFlowMode` 出现之前。
- 记忆点：条件动作的**第二个分支没有 `WFMenuItemTitle`**，语义是「否则」。

**C2 · 嵌套选择器不响应**
- 症状：iOS 上"选完一级后二级选择器不弹"。
- 根因：在菜单 case 里再嵌 `choosefromlist`/`choosefrommenu`，部分结构在真机上不触发。
- 修法：改成**两步走**——用 `dictionary` 存数据 + `getvalueforkey` 按键取值，再喂给一个平级的 `choosefromlist`。

**C3 · 字典的数组值写成对象数组**
- 症状：从字典取出来的列表是空的。
- 根因：数组值写成了 `WFDictionaryFieldValueItems`（对象数组）。
- 修法：数组值必须是**纯字符串数组**，包一层 `WFSerializationType: WFArrayParameterState`：
  ```json
  { "Value": ["外卖", "堂食"], "WFSerializationType": "WFArrayParameterState" }
  ```

**C4 · 位置敏感参数顺序错**
- 症状：写进去的字段全部**错位一格**，且不报错。
- 根因：App Intent 的 `values` 数组是**按位置**填进目标表单/字段的，顺序即列序。
- 修法：先核对目标 App 的表单列序，再对齐 `values`。

---

## D. 文件读写

**D1 · 写文件"假成功"（静默失败）**
- 症状：提示框照弹、显示成功，但目标文件里没有内容。
- 根因：文件类动作的**默认根目录是 `iCloud Drive/Shortcuts` 容器**，不是 iCloud Drive 根。用字符串路径写到别处会找不到父目录，**失败但不报错**。
- 修法：改用**文件书签**形态：
  ```
  WFFile = { fileLocation: { relativeSubpath: "com~apple~CloudDocs/目标目录",
                             WFFileLocationType: "iCloud", ... },
             filename: "目标目录", displayName: "目标目录" }
  WFFilePath = "文件名.csv"        # 只写纯文件名，追加到书签目录下
  ```
- 排查技巧：让它写一个纯文件名 `test.txt` 到"根"。如果它出现在 `iCloud Drive/Shortcuts` 下，就证实了默认根是 Shortcuts 容器。

**D2 · 文件书签无法程序伪造**
- 症状：手工拼的 plist 里的书签导入后失效。
- 根因：书签含 `crossDeviceItemID` 等**设备绑定标识**，由文件选择器写入。
- 修法：只能让用户**在 App 里选一次**；或**复制一份已含书签的导出版**当底版再改。

**D3 · 从 App 容器读不到外部文件**
- 症状：脚本/动作读不到期望路径下的文件。
- 根因：App 容器之间互相隔离（例如 Scriptable 容器 `iCloud~dk~simonbs~Scriptable/Documents` 与 iCloud Drive `com~apple~CloudDocs` 互不可达）。
- 修法：跨容器只有两条路——① 用文件书签由用户在目标 App 里选一次；② 用 App 的 URL scheme 调它的脚本，让脚本自己在自己容器里落盘。

---

## E. 签名

**E1 · 沙箱内签名失败**
- 症状：`shortcuts sign` 报 SSL / 连接失败。
- 根因：签名需联网调 Apple 服务，沙箱拦截。
- 修法：在沙箱外执行。

**E2 · 把 AEA1 当 plist 读**
- 症状：解析报错 / 乱码。
- 修法：先 `unpack` 解密，公钥从**该文件自身**证书链取（见 `signing.md`）。

**E3 · 名字丢了**
- 症状：导入后名称是文件名。
- 根因：签名会**剥掉 `WFWorkflowName`**。
- 修法：把文件名起好。

**E4 · 无害告警**
- 症状：`shortcuts sign` 刷一屏 `ERROR: Unrecognized attribute string flag '?' ...`。
- 修法：**忽略**。产物有效，用 `inspect` 回读确认即可。

**E5 · 多次签名证书不同**
- 症状：两次签同一文件，证书指纹不一样，怀疑签坏了。
- 修法：**这是正常行为**，每次签名都签发新证书。

---

## F. 兼容性

**F1 · 系统条目名不匹配**
- 症状：非英文系统上，写日历/提醒事项时行为异常或报错。
- 根因：显式指定了英文列表名（如 `WFCalendarItemCalendar`）。
- 修法：**省略该参数**，走系统默认列表。

**F2 · 中文/特殊字符进 URL**
- 症状：URL scheme 调用无效或参数丢失。
- 修法：必须**百分号编码**（Python：`urllib.parse.quote`）。

**F3 · App 未安装**
- 症状：导入后关键动作变成红字"未知动作"。
- 根因：该动作由某个 App 提供（App Intents），用户设备没装。
- 修法：在 README/说明里写明依赖；或改用系统动作降级实现。

---

## 一句话总结

改了 plist 之后，按这个顺序过一遍，基本不会翻车：

```
① validate_attachments.py   占位符对不对          （A1 A2）
② 数据来源              显式 WFInput？Date？   （A3 B1）
③ 控制流定位            GroupingIdentifier？   （C1）
④ 落表/落文件          顺序？路径？书签？        （C4 D1）
⑤ 签名                  沙箱外？回读验证？        （E1 E4）
```
