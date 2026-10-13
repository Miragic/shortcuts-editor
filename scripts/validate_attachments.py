#!/usr/bin/env python3
"""
validate_attachments.py — 校验记账快捷指令 .shortcut（XML plist）中
所有 WFTextTokenString 的 attachmentsByRange 与 U+FFFC 占位符是否一一对应。

用法:
    python3 validate_attachments.py <file.shortcut> [<file2.shortcut> ...]

规则:
    - string 里每个 U+FFFC (object replacement char) 是一个变量占位符
    - attachmentsByRange 的键 "{pos,len}" 必须指向一个 U+FFFC 的起始位置
    - 占位符数量必须 == attachments 数量，且不得重复 / 遗漏
    - 这是记账快捷指令最常见的崩溃点：变量引用错位（如应为 {9,1} 写成 {10,1}）

退出码: 0 = 全部通过, 1 = 发现问题。
"""
import sys
import re
import plistlib

PLACEHOLDER = "\ufffc"  # U+FFFC OBJECT REPLACEMENT CHARACTER
# 注意:系统序列化出的键形如 "{0, 1}"(逗号后有空格),
# 手工书写时常写成 "{0,1}"。两种都要接受,否则会对真实文件全量误报。
RANGE_RE = re.compile(r"^\{\s*(\d+)\s*,\s*(\d+)\s*\}$")


def find_token_nodes(obj, path="root"):
    """递归找到所有带有 string + attachmentsByRange 的 dict（即 WFTextTokenString 节点）。"""
    nodes = []
    if isinstance(obj, dict):
        if (
            "string" in obj
            and isinstance(obj["string"], str)
            and "attachmentsByRange" in obj
            and isinstance(obj["attachmentsByRange"], dict)
        ):
            nodes.append((path, obj))
        for k, v in obj.items():
            nodes.extend(find_token_nodes(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            nodes.extend(find_token_nodes(v, f"{path}[{i}]"))
    return nodes


def check_node(path, node, errors):
    s = node["string"]
    atts = node["attachmentsByRange"]
    placeholders = [i for i, ch in enumerate(s) if ch == PLACEHOLDER]

    if len(placeholders) != len(atts):
        errors.append(
            f"[{path}] 占位符数量({len(placeholders)}) != attachments 数量({len(atts)})"
        )

    used_positions = set()
    for key, _val in atts.items():
        m = RANGE_RE.match(key)
        if not m:
            errors.append(f"[{path}] 非法 range 键: {key!r}（应为 {{pos,len}} 或 {{pos, len}}）")
            continue
        pos, length = int(m.group(1)), int(m.group(2))
        if pos + length > len(s):
            errors.append(f"[{path}] range {key} 越界（string 长度 {len(s)}）")
            continue
        seg = s[pos : pos + length]
        if any(c != PLACEHOLDER for c in seg):
            errors.append(
                f"[{path}] range {key} 指向的不是占位符（实际片段={seg!r}）"
            )
        if pos in used_positions:
            errors.append(f"[{path}] range {key} 与另一 attachment 重复指向同一位置")
        used_positions.add(pos)

    for p in placeholders:
        if p not in used_positions:
            errors.append(f"[{path}] 位置 {p} 的占位符没有任何 attachment 引用")


def validate_file(path):
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
    except Exception as e:
        print(f"✗ {path}: 无法解析为 plist（若是签名 .shortcut，请先 aea decrypt 提取 Shortcut.wflow）— {e}")
        return False

    nodes = find_token_nodes(data)
    errors = []
    for p, node in nodes:
        check_node(p, node, errors)

    if errors:
        print(f"✗ {path}: 发现 {len(errors)} 处问题")
        for e in errors:
            print(f"    - {e}")
        return False
    print(f"✓ {path}: {len(nodes)} 个文本节点，占位符全部对应正确")
    return True


def main():
    if len(sys.argv) < 2:
        print("用法: python3 validate_attachments.py <file.shortcut> [...]")
        sys.exit(2)
    ok = True
    for p in sys.argv[1:]:
        if not validate_file(p):
            ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
