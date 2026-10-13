# 签名与解密往返

改动一个已签名的 `.shortcut`，完整链路是：

```
签名文件 ──解密──▶ 可编辑 plist ──改──▶ 校验 ──打包──▶ 明文 .shortcut ──签名──▶ 可导入的 .shortcut
```

---

## 1. 一键走完读写（推荐）

```bash
# 读：签名 / 明文都能吃，自动判断形态
python3 scripts/shortcuts_tool.py inspect  我的捷径.shortcut
python3 scripts/shortcuts_tool.py unpack   我的捷径.shortcut -o wf.plist

# ... 编辑 wf.plist ...

# 校验 → 打包 → 签名
python3 scripts/validate_attachments.py wf.plist
python3 scripts/shortcuts_tool.py pack  wf.plist -o 我的捷径_v2.shortcut
shortcuts sign --mode anyone --input 我的捷径_v2.shortcut --output 我的捷径_v2_signed.shortcut
```

下面三节是这套流程背后的原理与手写命令，排障时用得上。

---

## 2. 签名

```bash
shortcuts sign --mode anyone --input 待签.shortcut --output 已签.shortcut
```

- `--mode anyone`：无需原私钥，签出的文件可导入**任意**设备。这是最常用的模式。
- `--mode people-who-know-me`：只允许联系人导入（需要私钥能力，一般不用）。

**签名特性（必须知道）**：

| 现象 | 说明 |
|---|---|
| 每次生成**全新证书** | 同一文件签两次，证书指纹不同。这正常 |
| **剥掉 `WFWorkflowName`** | 导入后的名称取自**文件名**。想让用户看到正确名字，就先把文件名起好 |
| **必须联网** | 签名由 Apple 的签名服务完成 |
| **必须在沙箱外执行** | 沙箱内会 SSL 失败 |

> 终端可能刷出一串 `ERROR: Unrecognized attribute string flag '?' ...`。这是该命令在部分环境下的**无害告警**，签名产物仍然有效——用 `inspect` 回读即可确认。

---

## 3. 解密：签名文件不是 plist

AEA1 归档的结构：

```
[AEA1][version:4B][meta_len:4B little-endian][meta plist][加密数据...]
                          └─ SigningCertificateChain / SigningTime 等
```

手写解包命令（`shortcuts_tool.py unpack` 内部做的就是这些）：

```bash
# 1) 从文件头解出签名元数据，取出证书链第一张
python3 - <<'EOF'
import struct, plistlib
data = open('in.shortcut', 'rb').read()
assert data[:4] == b'AEA1', '不是 AEA1 归档'
meta_len = struct.unpack('<I', data[8:12])[0]
meta = plistlib.loads(data[12:12 + meta_len])
open('cert0.der', 'wb').write(meta['SigningCertificateChain'][0])
EOF

# 2) 证书转公钥
openssl x509 -inform der -in cert0.der -pubkey -noout -out cert0.pub.pem

# 3) 解密【整个文件】为 AppleArchive 归档
aea decrypt -sign-pub cert0.pub.pem -i in.shortcut -o decrypted.aar

# 4) 解出工作流
mkdir -p extract
aa extract -i decrypted.aar -d extract      # -> extract/Shortcut.wflow
```

**三个关键点**：

1. **解密的是整个文件**，不是 payload 之后的字节。只解密后半段会失败。
2. **公钥必须从该文件自身取。** `SigningCertificateChain[0]` 每次都不同，旧公钥不可复用于新文件。
3. 解出的 `Shortcut.wflow` 就是个 plist（可能是二进制或 XML），`plistlib` 直接读。

---

## 4. 实测记录（往返不变形验证）

以一份真实签名文件（50 个动作）跑完整往返，结果：

| 步骤 | 结果 |
|---|---|
| `unpack` 解密导出 | ✅ 50 个动作，`plistlib.load` 成功 |
| `pack` 重新打包 | ✅ 50 个动作 |
| 两次解包内容比对 | ✅ **完全一致**（除主动改写的 `WFWorkflowName`） |
| `validate_attachments.py` | ✅ 12 个文本节点，占位符全部对应正确 |
| `shortcuts sign` 重签 | ✅ 产出 AEA1 归档，证书为新签发、`WFWorkflowName` 已剥离 |
| 回读新签名文件 | ✅ 50 个动作，正常解析 |

结论：**「解开 → 改一处 → 装回去」不会破坏文件。** 只要校验通过、签名成功，改动就是可靠的。

> 校验方式：`plistlib.load` 两次结果做 dict 比较（`==`）。比对比对时记得把 `WFWorkflowName` 排除——签名本来就会剥掉它。

---

## 5. 报错对照

| 报错 / 现象 | 根因 | 处理 |
|---|---|---|
| `Unable to read plist` / 解析失败 | 直接把 AEA1 文件当 plist 读 | 先 `unpack` 解密 |
| `aea decrypt` 失败 / 公钥不匹配 | 用了旧的或别的文件的公钥 | 从**该文件自身**的证书链取 |
| `aea decrypt` 后 `aa extract` 报格式错 | 只解密了部分字节 | 解密整个文件 |
| `shortcuts sign` 报 SSL / 连接失败 | 在沙箱内执行 | 到沙箱外重跑 |
| `shortcuts sign` 刷 `Unrecognized attribute string flag` | 环境相关的无害告警 | 忽略；用 `inspect` 回读确认 |
| 签名成功但导入后名称不对 | `WFWorkflowName` 被剥离，名称取自文件名 | 改文件名 |
| 导入后提示「未指定 URL」/ 变量为空 | 文件本身有问题（不是签名问题） | 见 `pitfalls.md` |
| 改完导入没变化 | 导的还是旧的签名文件 | 确认导的是 `*_signed.shortcut` |
