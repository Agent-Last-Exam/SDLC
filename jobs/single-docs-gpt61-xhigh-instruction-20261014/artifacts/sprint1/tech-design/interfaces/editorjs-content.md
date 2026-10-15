# EditorJS v1 内容合同（I15）

版本：v1；这是技术设计选定的客户端支持集与资源保护值，不是 PRD 已给定的业务上限。公开输入仍使用既有 JSON/JSONString 字段，所有写入入口在持久化前应用同一校验器。

## 结构与大小

UTF-8 序列化输入不超过 1 MiB；blocks 最多 1000 个；单个富文本字符串最多 65536 字符；整个列表最多 10000 项。列表 items 根层记为深度 1，最大 L=8；L 合法、L+1 拒绝。必须先检查字节数与有限深度，再递归校验，不依靠不受限的 json.loads/遍历处理任意结构。空 blocks 是合法清空，不把 null 当空内容；可空业务字段的 null 仅按所属 mutation 的清空合同处理。

只允许下表字段，未知/额外字段拒绝，数组元素不能是 null。字段未标为必填即为可选；省略不生成不受信任默认数据。

| 节点 | 允许字段与类型 |
| --- | --- |
| 根 | `blocks`（必填数组）、`time`（非负有限整数）、`version`（最长 32 字符串） |
| block | `type`（必填）、`data`（必填对象）、`id`（最长 64 字符串）；不接受任意 tunes |
| paragraph.data | `text`（必填富文本字符串） |
| header.data | `text`（必填富文本字符串）、`level`（必填整数 1、2、3） |
| quote.data | `text`（必填富文本字符串）、`caption`（富文本字符串）、`alignment`（left/center，省略为 left） |
| list.data | `style`（必填 ordered/unordered）、`items`（必填数组）；接受整组旧字符串项或整组嵌套对象项，不接受混合项 |
| 嵌套 list item | `content`（必填富文本字符串）、`items`（可选同结构数组）；未提供 items 规范化为 [] |
| image.data | `file`（必填，仅含必填 url 字符串）、`caption`（富文本字符串）、`withBorder`/`stretched`/`withBackground`（布尔） |
| embed.data | `service`（必填 youtube/vimeo）、`source`/`embed`（必填 URL）、`width`/`height`（可选正整数，不超过 4096）、`caption`（富文本字符串） |

不新增未知 block 的宽松通用清理后保存行为。历史合法字符串列表和 image/embed 继续可读可编辑；超出支持集的历史内容不批量重写，编辑保存时明确指明位置和迁移原因，不能悄悄删除未知 block。Dashboard 序列化器只发本合同集合；客户端工具包升级如添加 meta/tunes，须先扩展共同合同并补兼容测试，不能直接透传。

## HTML、URL 与规范化

1. 结构通过后，用 HTML parser 而非正则解析 text/caption/content。允许标签 `b,strong,i,em,s,a,br`，没有任意样式、脚本、SVG、iframe 或事件属性。非链接标签不接受属性。链接只接受 href、title、target、rel；额外属性（含 on*、style）拒绝并返回字段定位。
2. HTML 实体解码并移除首尾空白后校验 href；控制字符、NUL、编码绕过、协议相对 `//`、data/javascript/vbscript/file/blob 及其他 scheme 一律拒绝。链接允许 http、https、mailto、tel、站内 `/path`（不得以 // 开头）及 `#anchor`；图片仅允许 http/https 与站内资源路径。embed 必须 https，source/embed 的域与所选服务官方 youtube.com/youtu.be 或 vimeo.com/player.vimeo.com 匹配，不能只检查字符串前缀。
3. target 只接受 `_self`、`_blank`；`_blank` 合并规范化 rel 中的 `noopener noreferrer`（不重复），不能用输入 rel 覆盖保护值。已有其他 rel 仅保留 `nofollow`。不接受任意命名窗口。
4. 清理只做通过验证后的规范化（大小写、空白、rel），不以 `#invalid` 替换危险链接后假称保存成功。所有块验证完成再返回新的深拷贝，绝不原地改半个对象。
5. scheme 白名单由代码和安全测试固定，无商店配置或 App 设置可放宽。输出渲染仍使用同一允许集防御历史数据；不从富文本验证器抓取图片或执行 iframe。

## 错误与原子性

mutation 使用原有域错误类型：code=INVALID；field 为实际公开输入路径，例如 `description.blocks[2].data.items[0].content`；message 为中文可翻译原因类别（STRUCTURE、UNKNOWN_FIELD、URL_SCHEME、LINK_ATTRIBUTE、DEPTH、SIZE），不回显危险 HTML 或 token。GraphQL JSON 标量解析失败采用 I23 的标准错误。产品、页面、属性富文本、分类、集合、商品类型及翻译入口统一使用，不因从翻译/扩展返回而跳过。任何失败不保存其他块或其他属于同一原子 mutation 的字段。

## 验证边界

验证现有 `core/utils/tests/test_editorjs.py` 合法 paragraph/list/image/embed 示例与 Dashboard `RichTextEditor/consts.ts` 支持工具；增加 header/quote、合法链接、嵌套 L/L+1、额外字段、entity 编码 scheme、opener 保护、size 临界值及多字段整体回滚用例。现有测试期望危险 URL 被替换为 #invalid 是 Base 行为差异，不修改冻结测试，研发新增目标断言并在差异报告说明。
