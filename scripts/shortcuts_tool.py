#!/usr/bin/env python3
"""
shortcuts_tool.py — 读取 / 解包 / 重打包 Apple 快捷指令（.shortcut）

三个子命令，对应「读取 → 编辑 → 写回」的三步：

    inspect  <file.shortcut>                  读取：打印动作序列、变量、占位符问题
    unpack   <file.shortcut> -o wf.plist      读取：导出成可编辑的 XML plist
    pack     <wf.plist> -o new.shortcut       写回：把 plist 打包成 .shortcut

签名文件（AEA1 归档）会自动解密（依赖 macOS 自带的 aea / aa 与 openssl）；
未签名的明文 plist 直接读取。

示例
----
    python3 shortcuts_tool.py inspect ~/Downloads/我的捷径.shortcut
    python3 shortcuts_tool.py unpack  ~/Downloads/我的捷径.shortcut -o wf.plist
    # ... 编辑 wf.plist ...
    python3 shortcuts_tool.py pack    wf.plist -o 我的捷径_v2.shortcut
    shortcuts sign --mode anyone --input 我的捷径_v2.shortcut --output 我的捷径_v2_signed.shortcut

退出码：0 成功；1 失败。
"""
import argparse
import importlib.util
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile

AEA_MAGIC = b"AEA1"

# 常见动作标识 → 可读名称。未收录的会退化成标识末尾，不影响使用。
ACTION_NAMES = {
    "is.workflow.actions.ask": "要求输入",
    "is.workflow.actions.gettext": "文本",
    "is.workflow.actions.text": "文本",
    "is.workflow.actions.comment": "注释",
    "is.workflow.actions.setvariable": "设定变量",
    "is.workflow.actions.getvariable": "获取变量",
    "is.workflow.actions.appendvariable": "追加到变量",
    "is.workflow.actions.choosefrommenu": "选择菜单",
    "is.workflow.actions.choosefromlist": "从列表选择",
    "is.workflow.actions.dictionary": "字典",
    "is.workflow.actions.getvalueforkey": "获取字典值",
    "is.workflow.actions.setvalueforkey": "设置字典值",
    "is.workflow.actions.list": "列表",
    "is.workflow.actions.date": "当前日期",
    "is.workflow.actions.format.date": "格式化日期",
    "is.workflow.actions.adjustdate": "调整日期",
    "is.workflow.actions.url": "URL",
    "is.workflow.actions.urlencode": "URL 编码",
    "is.workflow.actions.openurl": "打开 URL",
    "is.workflow.actions.downloadurl": "获取 URL 内容",
    "is.workflow.actions.addnewreminder": "添加提醒事项",
    "is.workflow.actions.addnewcalendar": "添加日历事件",
    "is.workflow.actions.showresult": "显示结果",
    "is.workflow.actions.alert": "显示提醒",
    "is.workflow.actions.notification": "显示通知",
    "is.workflow.actions.askforinput": "要求输入",
    "is.workflow.actions.setclipboard": "拷贝到剪贴板",
    "is.workflow.actions.getclipboard": "获取剪贴板",
    "is.workflow.actions.savetofile": "存储文件",
    "is.workflow.actions.file.append": "追加到文件",
    "is.workflow.actions.file.createfolder": "创建文件夹",
    "is.workflow.actions.getfile": "获取文件",
    "is.workflow.actions.getfilelink": "获取文件链接",
    "is.workflow.actions.documentpicker.open": "选择文件",
    "is.workflow.actions.selectphoto": "选择照片",
    "is.workflow.actions.takephoto": "拍照",
    "is.workflow.actions.extracttextfromimage": "从图像提取文本",
    "is.workflow.actions.runscript": "运行脚本",
    "is.workflow.actions.runjavascriptonwebpage": "在网页上运行 JS",
    "is.workflow.actions.runworkflow": "运行快捷指令",
    "is.workflow.actions.repeat.each": "对每个项目重复",
    "is.workflow.actions.repeat.count": "重复",
    "is.workflow.actions.conditional": "如果",
    "is.workflow.actions.exit": "停止此快捷指令",
    "is.workflow.actions.quicklook": "快速查看",
    "is.workflow.actions.waittocontinue": "等待",
    "is.workflow.actions.takescreenshot": "截屏",
    "is.workflow.actions.setbrightness": "设定亮度",
    "is.workflow.actions.speaktext": "朗读文本",
    "is.workflow.actions.showwebpage": "显示网页",
    "is.workflow.actions.getcurrentweather": "获取当前天气",
    "is.workflow.actions.count": "计数",
    "is.workflow.actions.number": "数字",
    "is.workflow.actions.calculate": "计算",
    "is.workflow.actions.text.match": "匹配文本",
    "is.workflow.actions.text.replace": "替换文本",
    "is.workflow.actions.text.split": "拆分文本",
    "is.workflow.actions.text.combine": "合并文本",
    "is.workflow.actions.format.number": "格式化数字",
    "is.workflow.actions.getitemfromlist": "从列表获取项目",
    "is.workflow.actions.setitemname": "设定名称",
    "is.workflow.actions.getnameofitem": "获取名称",
    "is.workflow.actions.filter.files": "筛选文件",
    "com.apple.Numbers.TNiOSAddValuesToFormIntent": "Numbers：向表单添加值",
    "com.apple.Numbers.TNiOSCreateSpreadsheetIntent": "Numbers：新建表格",
    "com.apple.mobilemail.SendEmailIntent": "邮件：发送",
}


# --------------------------------------------------------------------------
# 基础 I/O
# --------------------------------------------------------------------------
def run(cmd):
    """执行外部命令，失败时抛出带 stderr 的异常。"""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            "命令失败: %s\n%s" % (" ".join(cmd), (r.stderr or r.stdout).strip())
        )
    return r.stdout


def detect_kind(path):
    """返回 'aea'（已签名归档）/ 'plist'（明文，xml 或 binary）。"""
    with open(path, "rb") as f:
        head = f.read(4)
    if head == AEA_MAGIC:
        return "aea"
    return "plist"


def read_aea_meta(path):
    """从 AEA1 文件头解析签名元数据（证书链、签名时间等）。"""
    data = open(path, "rb").read()
    if len(data) < 12:
        raise RuntimeError("文件太短，不是有效的 AEA1 归档")
    meta_len = struct.unpack("<I", data[8:12])[0]
    return plistlib.loads(data[12:12 + meta_len])


def extract_aea(path, tmp):
    """解密 AEA1 并提取 Shortcut.wflow。返回 (workflow_dict, meta_dict)。"""
    meta = read_aea_meta(path)
    chain = meta.get("SigningCertificateChain") or []
    if not chain:
        raise RuntimeError("签名元数据里没有 SigningCertificateChain，取不到公钥")

    der = os.path.join(tmp, "cert0.der")
    pem = os.path.join(tmp, "cert0.pem")
    with open(der, "wb") as f:
        f.write(chain[0])
    run(["openssl", "x509", "-inform", "der", "-in", der, "-pubkey", "-noout", "-out", pem])

    aar = os.path.join(tmp, "decrypted.aar")
    run(["aea", "decrypt", "-sign-pub", pem, "-i", path, "-o", aar])

    outdir = os.path.join(tmp, "extract")
    os.makedirs(outdir, exist_ok=True)
    run(["aa", "extract", "-i", aar, "-d", outdir])

    wflow = None
    for root, _dirs, files in os.walk(outdir):
        for fn in files:
            if fn.endswith(".wflow"):
                wflow = os.path.join(root, fn)
                break
        if wflow:
            break
    if not wflow:
        raise RuntimeError("解包后没找到 .wflow 文件")

    with open(wflow, "rb") as f:
        return plistlib.load(f), meta


def load_shortcut(path):
    """统一入口：无论签名与否，都返回 (workflow_dict, meta_or_None, kind)。

    调用方负责在 finally 里清理返回的 tmpdir。
    """
    kind = detect_kind(path)
    if kind == "aea":
        tmp = tempfile.mkdtemp(prefix="shortcut_")
        try:
            wf, meta = extract_aea(path, tmp)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return wf, meta, kind, tmp
    with open(path, "rb") as f:
        return plistlib.load(f), None, kind, None


def load_validator():
    """复用同目录的 validate_attachments.py，保持占位符检查逻辑单一来源。"""
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(here, "validate_attachments.py")
    if not os.path.isfile(src):
        return None
    spec = importlib.util.spec_from_file_location("validate_attachments", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# 文本解析助手
# --------------------------------------------------------------------------
def action_id_name(ident):
    if ident in ACTION_NAMES:
        return ACTION_NAMES[ident]
    if ident.startswith("is.workflow.actions."):
        return ident[len("is.workflow.actions."):]
    return ident


def text_value(node):
    """从字符串 / WFTextTokenString 里取出可读文本。"""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        s = node.get("string")
        if isinstance(s, str):
            return s.replace("\ufffc", "⟨变量⟩")
    if isinstance(node, list):
        return "[%d 项]" % len(node)
    return None


def summarize_params(params):
    """给一个动作挑出最值得看的参数，拼成一行摘要。"""
    bits = []
    if "WFTextActionText" in params:
        t = text_value(params["WFTextActionText"])
        if t:
            bits.append(repr(t[:48]))
    if "WFMenuItems" in params and isinstance(params["WFMenuItems"], list):
        items = params["WFMenuItems"]
        shown = "、".join(str(i) for i in items[:4])
        bits.append("菜单[%d]: %s%s" % (len(items), shown, "…" if len(items) > 4 else ""))
    if "WFDictionaryKey" in params:
        bits.append("键=%s" % (text_value(params["WFDictionaryKey"]) or "⟨变量⟩"))
    if "WFVariableName" in params:
        bits.append("变量=%s" % params["WFVariableName"])
    if "WFItems" in params and isinstance(params["WFItems"], list):
        bits.append("字典 %d 项" % len(params["WFItems"]))
    if "WFDateActionMode" in params:
        bits.append("模式=%s" % params["WFDateActionMode"])
    if "WFDateFormat" in params:
        bits.append("格式=%s" % params["WFDateFormat"])
    if "WFInput" in params and not bits:
        bits.append("(有输入引用)")
    if "values" in params and isinstance(params["values"], list):
        bits.append("values %d 列" % len(params["values"]))
    if "WFRequestTextInputDefault" in params:
        bits.append("默认=%r" % str(params["WFRequestTextInputDefault"])[:20])
    if "WFMenuPrompt" in params:
        p = text_value(params["WFMenuPrompt"])
        if p:
            bits.append("提示=%r" % p[:20])
    return "  ".join(bits)


# --------------------------------------------------------------------------
# inspect
# --------------------------------------------------------------------------
def cmd_inspect(args):
    path = args.file
    try:
        wf, meta, kind, tmp = load_shortcut(path)
    except Exception as e:
        print("✗ 读取失败: %s" % e)
        return 1

    try:
        actions = wf.get("WFWorkflowActions") or []

        print("文件   : %s" % path)
        print("类型   : %s" % ("AEA1 签名归档（已解密）" if kind == "aea" else "明文 plist（未签名）"))
        if meta:
            chain = meta.get("SigningCertificateChain") or []
            if chain:
                der = os.path.join(tmp, "cert0.der")
                try:
                    info = run(["openssl", "x509", "-inform", "der", "-in", der,
                                "-noout", "-subject", "-dates"])
                    for line in info.strip().splitlines():
                        print("签名   : %s" % line.strip())
                except Exception:
                    pass
        print("工作流名: %r" % wf.get("WFWorkflowName"))
        print("动作数 : %d" % len(actions))
        print()

        if args.json:
            import json
            print(json.dumps(
                [{"index": i,
                  "identifier": a.get("WFWorkflowActionIdentifier"),
                  "name": action_id_name(a.get("WFWorkflowActionIdentifier") or ""),
                  "uuid": a.get("WFWorkflowActionParameters", {}).get("UUID"),
                  "parameters": {k: v for k, v in a.get("WFWorkflowActionParameters", {}).items()
                                 if k != "UUID"}}
                 for i, a in enumerate(actions)],
                ensure_ascii=False, indent=2, default=str))
            return 0

        print("动作序列:")
        # 控制流缩进：mode 0 = 块开始，1 = 分支（菜单 case），2 = 块结束
        # 注意 mode 是「同级并列」的：新开一个 case 要回到块的层级再进一格。
        blocks = []          # 每层块：[开启时的缩进深度, 块的动作标识]
        depth = 0
        set_vars, get_vars = [], []
        for a in actions:
            ident = a.get("WFWorkflowActionIdentifier") or "?"
            params = a.get("WFWorkflowActionParameters") or {}
            name = action_id_name(ident)
            mode = params.get("WFControlFlowMode")
            summary = summarize_params(params)

            if ident.endswith("setvariable") and params.get("WFVariableName"):
                set_vars.append(params["WFVariableName"])
            if ident.endswith("getvariable") and params.get("WFVariableName"):
                get_vars.append(params["WFVariableName"])

            pad = "  " * depth
            if mode == 0:
                print("%s▾ %s%s" % (pad, name, ("   " + summary) if summary else ""))
                blocks.append((depth, ident))
                depth += 1
            elif mode == 1:
                base, owner = blocks[-1] if blocks else (max(0, depth - 1), "")
                title = params.get("WFMenuItemTitle")
                if not title:
                    # 条件动作的第二个分支没有标题，语义上是「否则」
                    title = "否则" if "conditional" in owner else "（分支）"
                print("%s├ 「%s」" % ("  " * (base + 1), title))
                depth = base + 2
            elif mode == 2:
                base, _owner = blocks.pop() if blocks else (depth, "")
                print("%s└ 结束" % ("  " * base))
                depth = base
            else:
                uuid = params.get("UUID")
                print("%s· %s%s%s" % (pad, name, ("   " + summary) if summary else "",
                                      ("   [%s]" % uuid[:8]) if uuid else ""))

        print()
        print("设定过的变量: %s" % ("、".join(dict.fromkeys(set_vars)) or "（无）"))
        print("读取的变量  : %s" % ("、".join(dict.fromkeys(get_vars)) or "（无）"))
        missing = [v for v in dict.fromkeys(get_vars) if v not in set_vars]
        if missing:
            print("⚠️ 读取了但从未设定的变量: %s" % "、".join(missing))
        print()

        mod = load_validator()
        if mod:
            nodes = mod.find_token_nodes(wf)
            errs = []
            for p, node in nodes:
                mod.check_node(p, node, errs)
            if errs:
                print("占位符检查: %d 个文本节点，发现 %d 处问题 ✗" % (len(nodes), len(errs)))
                for e in errs[:12]:
                    print("    - %s" % e)
                if len(errs) > 12:
                    print("    …（其余 %d 处省略）" % (len(errs) - 12))
            else:
                print("占位符检查: %d 个文本节点，全部对应正确 ✓" % len(nodes))
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# unpack / pack
# --------------------------------------------------------------------------
def cmd_unpack(args):
    try:
        wf, meta, kind, tmp = load_shortcut(args.file)
    except Exception as e:
        print("✗ 读取失败: %s" % e)
        return 1
    try:
        out = args.output
        with open(out, "wb") as f:
            plistlib.dump(wf, f, fmt=plistlib.FMT_XML, sort_keys=False)
        n = len(wf.get("WFWorkflowActions") or [])
        print("✓ 已导出: %s" % out)
        print("  来源类型: %s" % ("AEA1 签名归档（已解密）" if kind == "aea" else "明文 plist"))
        print("  动作数  : %d" % n)
        print()
        print("  改完后请依次执行：")
        print("    python3 validate_attachments.py %s      # 校验占位符" % out)
        print("    python3 shortcuts_tool.py pack %s -o new.shortcut" % out)
        print("    shortcuts sign --mode anyone --input new.shortcut --output new_signed.shortcut")
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def cmd_pack(args):
    try:
        with open(args.file, "rb") as f:
            wf = plistlib.load(f)
    except Exception as e:
        print("✗ 无法解析 plist: %s" % e)
        return 1

    if not isinstance(wf, dict) or "WFWorkflowActions" not in wf:
        print("✗ 这不是快捷指令 plist（缺少 WFWorkflowActions 根键）")
        return 1

    if args.name:
        wf["WFWorkflowName"] = args.name

    # 打包成 XML plist；Apple 的 shortcuts sign 接受这一形态
    with open(args.output, "wb") as f:
        plistlib.dump(wf, f, fmt=plistlib.FMT_XML, sort_keys=False)

    print("✓ 已打包: %s  （%d 个动作%s）" % (
        args.output, len(wf["WFWorkflowActions"]),
        "，名称已设为 %r" % args.name if args.name else ""))
    print()
    print("  下一步签名（沙箱外执行，需要联网）：")
    print("    shortcuts sign --mode anyone --input %s --output %s" % (
        args.output, os.path.splitext(args.output)[0] + "_signed.shortcut"))
    return 0


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="读取 / 解包 / 重打包 Apple 快捷指令(.shortcut)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("示例")[1] if "示例" in __doc__ else None)
    sub = ap.add_subparsers(dest="cmd")

    p1 = sub.add_parser("inspect", help="读取并打印动作序列 / 变量 / 占位符问题")
    p1.add_argument("file")
    p1.add_argument("--json", action="store_true", help="以 JSON 输出（便于程序处理）")
    p1.set_defaults(func=cmd_inspect)

    p2 = sub.add_parser("unpack", help="导出为可编辑的 XML plist")
    p2.add_argument("file")
    p2.add_argument("-o", "--output", required=True)
    p2.set_defaults(func=cmd_unpack)

    p3 = sub.add_parser("pack", help="把 XML plist 打包回 .shortcut")
    p3.add_argument("file")
    p3.add_argument("-o", "--output", required=True)
    p3.add_argument("-n", "--name", help="顺带设置 WFWorkflowName")
    p3.set_defaults(func=cmd_pack)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
