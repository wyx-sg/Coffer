# macOS 公证 (Notarization)

> English: [macos-notarization.md](./macos-notarization.md)

在 Coffer 拿到付费 Apple Developer ID 之前，release 工作流产出的 `.dmg`
**未签名、未公证**。在 macOS 10.15+（Catalina 之后），Gatekeeper 会在
首次打开时把 app 隔离。用户的绕行方法之一：

- **右键 → 打开**（对某个 app 一次性绕过 Gatekeeper），或
- `xattr -d com.apple.quarantine /Applications/Coffer.app`

## 通往公证版构建的路径

当团队拿到入网的付费 Apple Developer ID 之后，按下面步骤在 release
工作流中启用代码签名与公证。

### 1. 生成签名证书

在 [Apple Developer portal](https://developer.apple.com/account/resources/certificates/list)：

1. 创建一份类型为 **"Developer ID Application"** 的新证书。
2. 下载 `.cer` 文件并在钥匙串访问中安装。
3. 把证书 + 私钥连同一个强密码一起导出为 `.p12`。
4. 把 `.p12` 进行 base64 编码：
   ```bash
   base64 -i /path/to/cert.p12 | pbcopy
   ```

### 2. 创建 GitHub 仓库 secrets

在 **Settings → Secrets and variables → Actions** 下添加以下 secrets：

| Secret 名                    | 值                                                      |
| ---------------------------- | ------------------------------------------------------- |
| `APPLE_CERTIFICATE`          | base64 编码后的 `.p12` 内容（来自 step 1）              |
| `APPLE_CERTIFICATE_PASSWORD` | 导出 `.p12` 时设置的密码                                |
| `APPLE_SIGNING_IDENTITY`     | `Developer ID Application: <你的姓名或组织> (<TeamID>)` |
| `APPLE_ID`                   | 你的 Apple ID 邮箱                                      |
| `APPLE_PASSWORD`             | 来自 [appleid.apple.com][] 的 app-specific 密码         |
| `APPLE_TEAM_ID`              | Apple Developer portal 中 10 位的 team ID               |

[appleid.apple.com]: https://appleid.apple.com/account/manage

### 3. 配置 Tauri 签名 bundle

在 `desktop/tauri.conf.json` 中**新增**一个 `macOS` 键（如果已经存在则
更新其中的 `signingIdentity`）：

```json
{
  "bundle": {
    "macOS": {
      "signingIdentity": null
    }
  }
}
```

当 `signingIdentity` 为 `null` 时，Tauri 会从环境变量读取
`APPLE_SIGNING_IDENTITY`（Tauri 2 的默认行为）。只有当你的 Tauri 版本
的环境变量路径走不通时，才把它显式设为字面字符串值。

### 4. 翻开 release.yml 中被禁用的步骤

在 `.github/workflows/release.yml` 里，把：

```yaml
- name: codesign + notarize (disabled — no Apple Developer ID yet)
  if: false
```

改成：

```yaml
- name: codesign + notarize
  if: startsWith(matrix.os, 'macos')
```

再用下面的 codesign + notarize 实际命令替换占位 `run:` 体。

### 5. 完整的 codesign + notarize 步骤

```yaml
- name: codesign + notarize
  if: startsWith(matrix.os, 'macos')
  env:
    APPLE_CERTIFICATE: ${{ secrets.APPLE_CERTIFICATE }}
    APPLE_CERTIFICATE_PASSWORD: ${{ secrets.APPLE_CERTIFICATE_PASSWORD }}
    APPLE_SIGNING_IDENTITY: ${{ secrets.APPLE_SIGNING_IDENTITY }}
    APPLE_ID: ${{ secrets.APPLE_ID }}
    APPLE_PASSWORD: ${{ secrets.APPLE_PASSWORD }}
    APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
  run: |
    # 把 .p12 导入一个临时 keychain，避免污染 GitHub-hosted runner 的
    # macOS 系统 keychain。
    KEYCHAIN_PASSWORD=$(openssl rand -base64 32)
    security create-keychain -p "$KEYCHAIN_PASSWORD" build.keychain
    security default-keychain -s build.keychain
    security unlock-keychain -p "$KEYCHAIN_PASSWORD" build.keychain
    echo "$APPLE_CERTIFICATE" | base64 -d > /tmp/cert.p12
    security import /tmp/cert.p12 -k build.keychain \
      -P "$APPLE_CERTIFICATE_PASSWORD" -T /usr/bin/codesign
    security set-key-partition-list \
      -S apple-tool:,apple: -s -k "$KEYCHAIN_PASSWORD" build.keychain

    # 对 artifacts 目录下每份 .dmg 做公证与 staple。
    # （cargo tauri build 已通过 APPLE_SIGNING_IDENTITY 签了 .app。）
    for dmg in artifacts/*.dmg; do
      xcrun notarytool submit "$dmg" \
        --apple-id  "$APPLE_ID" \
        --password  "$APPLE_PASSWORD" \
        --team-id   "$APPLE_TEAM_ID" \
        --wait
      xcrun stapler staple "$dmg"
    done

    # 清理临时 keychain。
    security delete-keychain build.keychain
```

> **注**：`cargo tauri build`（在上一步运行）会从环境读到
> `APPLE_SIGNING_IDENTITY` 并在 bundle 阶段签 `.app`。上面的 notarytool
> 步骤在 `tauri build` 之后跑，把产出的 `.dmg` 提交给 Apple 公证服务。

## 验证签名构建

```bash
# 确认 app 已被正确代码签名
codesign -dv --verbose=4 /Applications/Coffer.app

# 确认 Gatekeeper 会放行运行而不弹隔离提示
spctl --assess --type execute --verbose /Applications/Coffer.app
```

`spctl` 预期输出：

```
/Applications/Coffer.app: accepted
source=Notarized Developer ID
```
