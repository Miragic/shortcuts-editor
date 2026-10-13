# assets/ — 放你自己的快捷指令模板

本目录**出厂不含任何 `.shortcut` 模板**。

## 为什么留空

快捷指令的导出件里，只要涉及"写文件"就会带**设备绑定的文件书签**（含 `crossDeviceItemID` 等标识）。这种文件：

- 在别人设备上导入后，书签指向的位置很可能失效；
- 程序**无法伪造**（见 `../references/pitfalls.md` D2）。

所以不适合随 skill 分发。

## 你可以放什么

把你**自己导出的、确定没有隐私内容**的 `.shortcut` 放进来当起点：

```bash
# 从 iPhone 导出后用 inspect 看一眼内容
python3 ../scripts/shortcuts_tool.py inspect your_template.shortcut

# 确认无隐私信息后放到这里
cp your_template.shortcut ./
```

之后就可以基于它做改动：

```bash
python3 ../scripts/shortcuts_tool.py unpack your_template.shortcut -o wf.plist
# 改 wf.plist
python3 ../scripts/validate_attachments.py wf.plist
python3 ../scripts/shortcuts_tool.py pack wf.plist -o new.shortcut
```

## 没有模板也能用

**`inspect` 任何现成的快捷指令就是最好的起点。** 不需要预置模板——从零写 plist 的话，直接看 `../references/file-format.md`。

## 发布前自查

如果你打算把放了模板的版本分享出去，先扫一遍隐私字段：

```bash
# 设备绑定标识 / 个人路径 / 个人文件名
grep -o 'crossDeviceItemID\|fileProviderDomainID\|com~apple~CloudDocs/[^<]*\|/Users/[^<]*' *.shortcut
```
