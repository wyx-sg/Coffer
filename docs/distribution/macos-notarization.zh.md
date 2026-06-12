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

在 `desktop/tauri.conf.json` 中**新增**一个 `macOS` 键（`bundle` 块已存在，
目前没有 `macOS` 键）：

```json
{
  "bundle": {
    "macOS": {
      "signingIdentity": null,
      "entitlements": "entitlements.plist"
    }
  }
}
```

当 `signingIdentity` 为 `null` 时，Tauri 会从环境变量读取
`APPLE_SIGNING_IDENTITY`（Tauri 2 的默认行为）。只有当你的 Tauri 版本
的环境变量路径走不通时，才把它显式设为字面字符串值。`entitlements` 路径
把已随仓库存在的 hardened-runtime 授权文件 `desktop/entitlements.plist`
接上——这些授权是必需的，因为被打包的 `coffer-daemon` / `coffer-mcp-shim`
PyInstaller sidecar 在公证强制的 hardened runtime 下运行，需要
`disable-library-validation` 与 `allow-unsigned-executable-memory`。

### 4. 在 release.yml 中新增 codesign + notarize 步骤

`.github/workflows/release.yml` 今天并没有一个被禁用的签名步骤——`bundle`
job 里（在 `install Tauri CLI` 与 `cargo tauri build` 之间）只有一段注释，
说明签名被推迟，以免未使用的 `APPLE_*` secrets 出现在仓库 secret 审计里。
要启用签名，用下面的步骤替换那段注释。

签名分布在 job 的两个位置，顺序如下：

1. **在 `cargo tauri build` 之前**（即今天那段注释所在的位置）：把证书导入
   一个临时 keychain，让构建得以签 `.app`。`cargo tauri build` 会从环境读到
   `APPLE_SIGNING_IDENTITY`，并在 bundle 阶段对 `.app` 做代码签名（带上
   step 3 的 entitlements），所以也要把 step 5 的 `env:` 块加到
   `cargo tauri build` 步骤上。
2. **在 `collect artifacts (macOS)` 之后**（此时 `.dmg` 才存在）：对它做公证
   与 staple。并在构建已签名后，去掉该 collect 步骤里的 `-unsigned` 改名逻辑。

step 5 中的合并步骤为便于阅读把两半放在一起；实际接入时，请把 keychain 导入
部分（build 之前）与 `notarytool` 循环（collect 之后）拆开，以遵循上述顺序。

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
