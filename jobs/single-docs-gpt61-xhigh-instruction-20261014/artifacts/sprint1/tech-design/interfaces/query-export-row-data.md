# 只读查询导出 row.data 合同（I11）

版本 v1；用于 `ProductExportRow.data: JSON!`、`GiftCardExportRow.data: JSON!`，不在 Query 中生成文件或任务。SDL 的 JSON 标量无法表达下面的字段约束，前后端必须共同校验。未知字段拒绝或按版本不支持处理，不能任意透传数据库列。

## 完整数据形状

```typescript
type MoneyData = { amount: string; currency: string }; // 有限十进制字符串，不用JSON浮点累计
type WeightData = { value: string; unit: "G" | "KG" | "OZ" | "LB" | "TONNE" };
type NamedRef = { id: string; name: string };
type MediaData = { id: string; type: string; url: string; alt: string };
type AttributeData = { id: string; name: string; values: { id: string; name: string | null; value: string | null }[] };
type StockData = { warehouseId: string; quantity: number; allocated: number; available: number };
type ChannelPriceData = { channelId: string; currency: string; price: MoneyData | null };
type VariantData = {
  id: string;
  sku?: string | null;
  weight?: WeightData | null;
  media?: MediaData[];
  attributes?: AttributeData[];
  stocks?: StockData[];
  prices?: ChannelPriceData[];
};
type ProductData = {
  id: string; // 始终与row.id相同；一个row是一个Product，不是一个Variant
  name?: string;
  description?: string | null; // 经I15规范化的EditorJS JSON字符串
  productType?: NamedRef;
  category?: NamedRef | null;
  weight?: WeightData | null;
  collections?: NamedRef[];
  chargeTaxes?: boolean;
  media?: MediaData[];
  attributes?: AttributeData[];
  channels?: { id: string; slug: string; currency: string; isPublished: boolean }[];
  variants?: VariantData[];
};
type GiftCardData = {
  id: string;
  displayCode: string; // 现有脱敏末位识别，不是全code
  currency: string;
  currentBalance: MoneyData;
  initialBalance: MoneyData;
  authorizedBalance: MoneyData;
  availableBalance: MoneyData;
  isActive: boolean;
  expiryDate: string | null; // ISO Date YYYY-MM-DD，非locale格式
};
```

全部 ID 为对应对象 Relay ID，不使用名称作为关联键；关联数组及元素均不可 null，合法没有结果为 `[]`。Weight/Money 的字符串为无分组符标准十进制，不允许 NaN/Infinity；日期与货币仅作为数据，不预格式化中文/英文显示。stock quantity/allocated/available 使用当前相同库存服务事实，不在前端重算，员工仓库范围仍生效。价格是当前渠道变体价格，不是历史订单冻结价。图库仅普通同步状态，不添加异步抓取专用字段。

## 商品投影和缺省

`exportInfo` 缺省输出 `id,name,productType,variants[{id,sku}]`。提供 `exportInfo.fields` 时只输出下面指定列及必要的 `id`/结构容器；显式 `fields:[]` 不等“所有列”，仅输出id和另行显式选择的关联列。某投影未选择的属性**省略**，选择后合法不存在才用合同允许的 null/[]。

| Base ProductFieldEnum | data投影 |
| --- | --- |
| NAME | name |
| DESCRIPTION | description |
| PRODUCT_TYPE | productType |
| CATEGORY | category |
| PRODUCT_WEIGHT | weight |
| COLLECTIONS | collections |
| CHARGE_TAXES | chargeTaxes |
| PRODUCT_MEDIA | media |
| VARIANT_ID | variants[].id |
| VARIANT_SKU | variants[].id、sku |
| VARIANT_WEIGHT | variants[].id、weight |
| VARIANT_MEDIA | variants[].id、media |

`exportInfo.attributes` 仅投影所选属性的product.attributes与variant.attributes；`warehouses` 仅投影所选仓库stocks；`channels` 仅投影所选渠道channels及variant.prices。数组内 ID OR、不同集合 AND 各自的字段授权，空数组不输出该关联，不作为无界全选。channel查询约束与所选输出channels取交集；不得因为exportInfo选择另一渠道就突破输入/权限范围。unknown/wrong-type关联ID为INVALID_ARGUMENT，不把无权限列静默输出或假null。

GiftCardData固定输出上面脱敏字段，不接受商品ExportInfo，也不输出完整code。如旧合法业务确需完整gift card code，继续现行有权legacy export mutation及owner文件保护；新只读查询不能因MANAGE_PRODUCTS或目录只读权限泄露卡密码。gift可用余额与I07同账本语义，不能将授权占用重复从currentBalance扣除。

VoucherCodeExportRow 不使用JSON：`id:ID!`、`voucherId:ID!`、`code:String!`，仅有MANAGE_DISCOUNTS并满足voucher/code范围者可读取；ids与voucherId交集。

## 文件与分页

一个Product row中的variants可有多项。CSV/XLSX flatten 由前端明确按variant展开：没有variants时保留product基本行；有多variant时重复product列但不重复当成多产品统计。数组关联列使用稳定顺序及明确分隔/JSON编码，不依据分页序号伪造ID。输出CSV公式转义不改变服务端合法源数据，货币附currency，重量附unit。

所有页成功才提供文件；任何页GraphQL/权限/游标错误不下载部分内容并冒充完成。合法0结果可下载仅列标题。动态数据改变期间不承诺跨多次请求永久快照；同静态集合和相同输入下连接稳定、有主键tie-break。大数据legacy降级必须先获得完整有效范围ids，不能丢锁定条件回退ALL。
