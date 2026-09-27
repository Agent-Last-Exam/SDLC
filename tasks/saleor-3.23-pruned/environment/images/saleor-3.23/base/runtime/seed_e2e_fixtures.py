"""Seed the fixtures saleor-dashboard's Playwright #e2e suite expects.

Upstream runs these tests against a Saleor Cloud snapshot -- see
saleor-dashboard/docs/running-tests.md:

    The tests are based on Saleor Cloud and use snapshots with prepared data.
    If you want to run those tests on your infrastructure you should update
    test data with your own created objects.

so playwright/data/e2eTestData.ts hardcodes 120 GraphQL IDs that encode that
snapshot's primary keys (base64 "Attribute:732" -> "QXR0cmlidXRlOjczMg==").
`populatedb` creates generic demo data with different keys and names, so every
test that opens an existing object by id fails.

This recreates those objects at their exact primary keys. Every id, name, slug,
price and SKU below is transcribed from e2eTestData.ts -- the line references in
each function point at the source block.

The suite is destructive (it deletes attributes, channels, menus...), so this is
idempotent and resets the states tests depend on. run-tests.sh invokes it before
each dash-e2e run, not once at build time.

Usage:
    python /workspace/seed_e2e_fixtures.py [tier ...]     # default: all
"""

import os
import sys
import uuid
from decimal import Decimal

import django

# Running by absolute path puts this file's directory on sys.path, not the
# project root, so `saleor.settings` would not resolve.
sys.path.insert(0, "/workspace/saleor")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "saleor.settings")
django.setup()

from django.db import connection  # noqa: E402
import datetime  # noqa: E402
from django.utils import timezone  # noqa: E402

from saleor.account.models import Address, Group, User  # noqa: E402
from saleor.app.models import App  # noqa: E402
from saleor.attribute.models import Attribute, AttributeValue  # noqa: E402
from saleor.channel.models import Channel  # noqa: E402
from saleor.giftcard.models import GiftCard  # noqa: E402
from saleor.menu.models import Menu, MenuItem  # noqa: E402
from saleor.page.models import PageType  # noqa: E402
from saleor.permission.models import Permission  # noqa: E402
from saleor.product.models import (  # noqa: E402
    Category,
    Collection,
    CollectionChannelListing,
    Product,
    ProductChannelListing,
    ProductType,
    ProductVariant,
    ProductVariantChannelListing,
)
from saleor.shipping.models import ShippingMethod, ShippingZone  # noqa: E402
from saleor.warehouse.models import Warehouse  # noqa: E402

REPORT = []


def note(msg):
    REPORT.append(msg)
    print(f"  {msg}")


def bump(model):
    """Explicit-pk rows and populatedb rows share one sequence."""
    if not model._meta.pk.db_returning:
        return
    table, pk = model._meta.db_table, model._meta.pk.column
    with connection.cursor() as cur:
        cur.execute(
            "SELECT pg_get_serial_sequence(%s, %s) IS NOT NULL", [table, pk]
        )
        if not cur.fetchone()[0]:
            return
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, %s), "
            f"GREATEST((SELECT COALESCE(MAX({pk}), 1) FROM {table}), 1))",
            [table, pk],
        )


def slugify(name):
    out = []
    for ch in name.lower():
        out.append(ch if ch.isalnum() else "-")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def uid(encoded):
    """Decode a UUID out of an e2eTestData.ts GraphQL id."""
    import base64

    raw = encoded.replace("%3D", "=")
    decoded = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode()
    return uuid.UUID(decoded.split(":", 1)[1])


ATTR_DEFAULTS = {
    "input_type": "dropdown",
    "value_required": False,
    "visible_in_storefront": True,
    "filterable_in_dashboard": True,
    "storefront_search_position": 0,
}


def tier_attributes():
    """e2eTestData.ts:1-51 ATTRIBUTES."""
    # (pk, name, type) -- "content" attributes are page attributes, which is
    # what the dashboard's content-attribute tab lists.
    specs = [
        (732, "e2e product attribute to be updated", "product-type"),
        (733, "e2e content attribute to be updated", "page-type"),
        (734, "e2e product attribute to be deleted", "product-type"),
        (735, "e2e content attribute to be deleted", "page-type"),
        (740, "e2e product attribute to be updated 1", "product-type"),
        (739, "e2e content attribute to be updated 2", "page-type"),
    ]
    for pk, name, atype in specs:
        Attribute.objects.update_or_create(
            pk=pk,
            defaults={"name": name, "slug": slugify(name), "type": atype,
                      **ATTR_DEFAULTS},
        )

    # SALEOR_127 deletes one value and edits another on the two
    # "...to be updated" attributes.
    for pk, name, _ in specs[:2]:
        attr = Attribute.objects.get(pk=pk)
        base = name.replace(" to be updated", "")
        for suffix in ("value to be deleted", "value to be updated"):
            vname = f"{base} {suffix}"
            AttributeValue.objects.update_or_create(
                attribute=attr, slug=slugify(vname), defaults={"name": vname}
            )

    for i in (1, 2, 3):
        name = f"e2e attribute to be bulk deleted {i}/3"
        Attribute.objects.update_or_create(
            slug=slugify(name),
            defaults={"name": name, "type": "product-type", **ATTR_DEFAULTS},
        )

    name = "Attribute to be assigned to page type"
    Attribute.objects.update_or_create(
        slug=slugify(name),
        defaults={"name": name, "type": "page-type", **ATTR_DEFAULTS},
    )

    bump(Attribute)
    bump(AttributeValue)
    note(f"attributes: {Attribute.objects.filter(pk__in=[p for p, _, _ in specs]).count()}/6 by pk")


def tier_page_types():
    """e2eTestData.ts:689-704 PAGE_TYPES."""
    specs = [
        (34, "A page type to be edited"),
        (35, "A page type to be removed"),
        (36, "a page type to be bulk deleted 1/2"),
        (37, "a page type to be bulk deleted 2/2"),
    ]
    for pk, name in specs:
        PageType.objects.update_or_create(
            pk=pk, defaults={"name": name, "slug": slugify(name)}
        )

    # SALEOR_188 renames page type 34 and assigns "Attribute to be assigned to
    # page type" to it. The assign dialog lists only UNassigned attributes, so
    # a re-run finds "No results found" unless the assignment is undone.
    PageType.objects.get(pk=34).attributepage.all().delete()

    bump(PageType)
    note(f"page types: {PageType.objects.filter(pk__in=[p for p, _ in specs]).count()}/4 by pk")


def tier_product_types():
    """e2eTestData.ts:705-720 PRODUCT_TYPES, plus PRODUCTS.singleProductType."""
    specs = [
        (672, "Single product type"),
        # Not in e2eTestData.ts: productCreateDialog.ts:16 defaults to the
        # product type named "Beer" for SALEOR_3's with-variants flow, so it is
        # snapshot data too. populatedb only creates "Juice".
        (671, "Beer"),
        (698, "A product type to be edited"),
        (699, "A product type to be removed"),
        (700, "a product type to be bulk deleted 1/2"),
        (701, "a product type to be bulk deleted 2/2"),
    ]
    for pk, name in specs:
        # SALEOR_184 calls makeProductShippableWithWeight(), which *toggles* the
        # "shipping required" checkbox and then fills the weight field -- that
        # field only renders while shipping is required, and the test asserts
        # the box ends up checked. So 698 must start unchecked. update_or_create
        # (not get_or_create) also resets the name the test randomises.
        ProductType.objects.update_or_create(
            pk=pk,
            defaults={
                "name": name,
                "slug": slugify(name),
                "kind": "normal",
                # SALEOR_5 uses 672 for the "product without variants" flow.
                "has_variants": pk != 672,
                "is_shipping_required": pk != 698,
                "weight": 0,
            },
        )
    bump(ProductType)
    note(f"product types: {ProductType.objects.filter(pk__in=[p for p, _ in specs]).count()}/{len(specs)} by pk")


def tier_categories():
    """e2eTestData.ts:208-220 CATEGORIES, plus TRANSLATIONS.translationsToBeAdded
    (Category:512)."""
    specs = [
        (507, "a category to be updated"),
        (511, "e2e category"),
        (512, "CategoryToTranslate"),
    ]
    for pk, name in specs:
        Category.objects.update_or_create(
            pk=pk, defaults={"name": name, "slug": slugify(name)}
        )
    for i in (1, 2):
        name = f"a cateogry to be bulk deleted {i}/2"  # sic, upstream typo
        Category.objects.update_or_create(
            slug=slugify(name), defaults={"name": name}
        )
    # Category declares objects=Manager() and tree=TreeManager(); only the
    # latter has rebuild(). Explicit pks leave MPTT fields inconsistent.
    Category.tree.rebuild()
    bump(Category)
    note(f"categories: {Category.objects.filter(pk__in=[p for p, _ in specs]).count()}/3 by pk")


def tier_collections():
    """e2eTestData.ts:221-233 COLLECTIONS, plus TRANSLATIONS.translationsToBeCleared
    (Collection:1, "Summer collection")."""
    specs = [
        (1, "Summer collection"),
        (166, "Collection to be updated"),
        (167, "e2e collection"),
    ]
    for pk, name in specs:
        Collection.objects.update_or_create(
            pk=pk, defaults={"name": name, "slug": slugify(name)}
        )
    for i in (1, 2):
        name = f"Collection to be deleted {i}/2"
        Collection.objects.update_or_create(
            slug=slugify(name), defaults={"name": name}
        )

    # SALEOR_113 assigns a product to collection 166. AssignProductDialogMulti
    # disables a product's checkbox unless its channel listings intersect the
    # collection's (isProductAvailableInVoucherChannels), and the test asserts
    # exactly 1 assigned row afterwards -- so it must start empty, or a re-run
    # toggles the checkbox off instead of on.
    collection = Collection.objects.get(pk=166)
    # Left EMPTY on purpose: SALEOR_113 assigns a product and then asserts
    # exactly 1 assigned row, so a pre-assigned product would make the dialog
    # checkbox a toggle-OFF and unassign it instead.
    #
    # KNOWN UNRESOLVED: that test still fails here. CollectionAssignProduct
    # (collections/mutations.ts:30) returns only `errors` -- not the collection
    # or its products -- and graphql/client.ts declares no typePolicy or
    # refetchQueries for it, so Apollo never refreshes CollectionProducts and the
    # page keeps showing "No products found" even though the row is in the DB
    # (verified: the GraphQL query with the same sortBy returns Bean Juice).
    collection.products.clear()
    for channel in Channel.objects.all():
        CollectionChannelListing.objects.update_or_create(
            collection=collection, channel=channel,
            defaults={"is_published": True},
        )
    bump(Collection)
    note(f"collections: {Collection.objects.filter(pk__in=[p for p, _ in specs]).count()}/3 by pk")


def tier_menus():
    """e2eTestData.ts:632-652 NAVIGATION_ITEMS."""
    specs = [
        (35, "e2e-menu-to-be-updated"),
        (39, "e2e-menu-to-be-deleted-from-list"),
        (40, "e2e-menu-to-be-deleted-from-details-view"),
    ]
    for pk, name in specs:
        Menu.objects.update_or_create(
            pk=pk, defaults={"name": name, "slug": slugify(name)}
        )
    for i in (1, 2):
        name = f"e2e-menu-to-be-bulk-deleted {i}/2"
        Menu.objects.update_or_create(slug=slugify(name), defaults={"name": name})

    # SALEOR_198 edits one item and deletes another; their `link` fields point
    # at categories by name.
    menu = Menu.objects.get(pk=35)
    menu.items.all().delete()
    for iname, link in [
        ("e2e-menu-item-to-be-updated", "Groceries"),
        ("e2e-menu-item-to-be-deleted", "Accessories"),
    ]:
        MenuItem.objects.create(
            menu=menu, name=iname,
            category=Category.objects.filter(name=link).first(),
        )
    bump(Menu)
    bump(MenuItem)
    note(f"menus: {Menu.objects.filter(pk__in=[p for p, _ in specs]).count()}/3 by pk")


def tier_channels():
    """e2eTestData.ts:247-274 CHANNELS.

    channelUSD (2243) / channelPLN (2244) are referenced BY NAME only, and
    populatedb already creates "Channel-USD" (pk 1, slug default-channel, the
    configured DEFAULT_CHANNEL_SLUG) and "Channel-PLN" (pk 2). Recreating them
    at the snapshot pks would duplicate those names and break the tests that
    match on them, so only the id-referenced channels are seeded here.
    """
    specs = [
        (2391, "a channel to be edited", "a-channel-to-be-edited", "USD"),
        (2394, "e2e-channel-do-not-delete", "e2e-channel-do-not-delete", "USD"),
    ]
    for pk, name, slug, currency in specs:
        Channel.objects.update_or_create(
            pk=pk,
            defaults={"name": name, "slug": slug, "currency_code": currency,
                      "default_country": "US", "is_active": True},
        )
    for name, currency in [
        ("z - channel to be deleted", "USD"),
        ("a channel for tax tests", "USD"),
    ]:
        Channel.objects.update_or_create(
            slug=slugify(name),
            defaults={"name": name, "currency_code": currency,
                      "default_country": "US", "is_active": True},
        )
    # OrderCreateDialog selects this exact name; SALEOR_78 asserts EUR
    # transactions on orders belonging to this channel.
    from saleor.channel import MarkAsPaidStrategy

    Channel.objects.update_or_create(
        slug="transaction-flow-channel",
        defaults={
            "name": "transaction flow channel", "currency_code": "EUR",
            "default_country": "PL", "is_active": True,
            "order_mark_as_paid_strategy": MarkAsPaidStrategy.TRANSACTION_FLOW,
        },
    )
    bump(Channel)
    note(f"channels: {Channel.objects.filter(pk__in=[p for p, _, _, _ in specs]).count()}/2 by pk")


def tier_warehouses():
    """e2eTestData.ts:297-322 WAREHOUSES. Warehouse pk is a UUID.

    warehouseEurope/Americas/Oceania/Africa are referenced BY NAME only
    (shippingMethods.spec.ts:139-144) and populatedb already creates all four,
    so seeding them at the snapshot UUIDs would just duplicate the names --
    same reasoning as channelUSD/channelPLN in tier_channels.
    """
    specs = [
        ("V2FyZWhvdXNlOjgzNGQwYjQwLWMwZGItNGRhZi04N2RjLWQ2ODBiYzY3NGVlMw%3D%3D",
         "warehouse to be edited"),
    ]
    def ensure_warehouse(name, pk=None):
        """Warehouse.address is PROTECT, so only mint an Address when creating."""
        lookup = {"pk": pk} if pk else {"slug": slugify(name)}
        existing = Warehouse.objects.filter(**lookup).first()
        if existing:
            if existing.name != name:
                existing.name = name
                existing.save(update_fields=["name"])
            return existing
        addr = Address.objects.create(
            first_name="e2e", last_name="warehouse", street_address_1="Teczowa 7",
            city="WROCLAW", postal_code="53-601", country="PL",
        )
        return Warehouse.objects.create(
            name=name, slug=slugify(name), address=addr,
            **({"pk": pk} if pk else {}),
        )

    for enc, name in specs:
        ensure_warehouse(name, pk=uid(enc))

    # WAREHOUSES.warehouseToBeDeleted.name is "warehouseto be deleted", which
    # is NOT the warehouse's name -- it is the already-transformed test-id
    # fragment. WarehouseList.tsx:113 builds the id as
    #   "warehouse-entry-" + name.toLowerCase().replace(" ", "")
    # and JS's string-argument replace() drops only the FIRST space, so the
    # real name is "warehouse to be deleted".
    ensure_warehouse("warehouse to be deleted")

    # SALEOR_101 ends with `expect(list).not.toContainText("warehouseto be
    # deleted")`, a substring check -- so any warehouse whose name contains that
    # fragment fails the assertion even after the right one is deleted. Drop
    # leftovers from earlier runs (including the literal mis-seeded name).
    Warehouse.objects.filter(name="warehouseto be deleted").delete()
    Warehouse.objects.filter(name__startswith="e2e test - warehouse").delete()

    # SALEOR_100 renames "warehouse to be edited"; restore it so re-runs work.
    Warehouse.objects.filter(pk=uid(specs[0][0])).update(
        name=specs[0][1], slug=slugify(specs[0][1])
    )

    have = Warehouse.objects.filter(pk__in=[uid(e) for e, _ in specs]).count()
    note(f"warehouses: {have}/1 by pk (Europe/Americas/Oceania/Africa from populatedb)")


def _publish_product(product, price=None, channels=None):
    """Give a product channel listings, plus variant listings.

    The dashboard filters product lists by channel, and the assign dialogs
    disable rows whose product has no listing in the relevant channel.

    `channels` limits publication -- PRODUCTS.productAvailableOnlyInPlnChannel /
    ...InUsdChannel are named for being single-channel, and publishing them
    everywhere both breaks that meaning and pads the channel-filtered pickers.
    """
    for channel in (channels if channels is not None else Channel.objects.all()):
        ProductChannelListing.objects.update_or_create(
            product=product, channel=channel,
            defaults={
                "is_published": True,
                "visible_in_listings": True,
                "currency": channel.currency_code,
                "available_for_purchase_at": timezone.now(),
                "published_at": timezone.now(),
            },
        )
    if price is None:
        return
    for variant in product.variants.all():
        for channel in (channels if channels is not None else Channel.objects.all()):
            ProductChannelListing.objects.filter(
                product=product, channel=channel
            ).update(discounted_price_amount=Decimal(price))
            ProductVariantChannelListing.objects.update_or_create(
                variant=variant, channel=channel,
                defaults={
                    "price_amount": Decimal(price),
                    "discounted_price_amount": Decimal(price),
                    "currency": channel.currency_code,
                },
            )


def tier_products():
    """e2eTestData.ts:323-432 PRODUCTS, plus the fixtures other specs need by
    name: SALEOR_103 asserts category 507's product tab lists "beer to be
    updated"; navigation.spec.ts hardcodes the category name "Polo Shirts"
    while populatedb_data.json spells it "Polo shirts".
    """
    ptype = ProductType.objects.get(pk=672)

    # (pk, name, category_pk, variant_pk, variant_name, sku, price)
    specs = [
        # SALEOR_46 adds a variant to this product and then reads the variants
        # data grid, which does not render at all without an existing row.
        (761, "Single product type to be updated", None, 1244, "base", "SPTU-BASE", 30),
        (763, "a beer available only in pln channel", None, None, None, None, None),
        (764, "a beer available only in USD channel", None, None, None, None, None),
        (729, "beer with variants", None, None, None, None, None),
        (733, "product that contains single variant", None, 1231, "single", None, None),
        (757, "beer to be deleted", None, 1230, "only", None, None),
        (765, "product with variant which will be updated", None, 1232,
         "update variant", None, None),
        (766, "juice with variant to be deleted", None, 1233, "bulk-1", None, None),
        (767, "beer with variant to be deleted", None, 1236, "to delete", None, None),
        (770, "e2e-do-not-touch", None, 1239, "TEST-123", "TEST-123", 100),
        (76, "Coconut Juice transaction flow", None, 1240, "84725784", "84725784", 10),
        # e2eProduct1/2 and e2eProductWithVariant1/2. The promotion-rule dialogs
        # pick these by name, and the variant names are asserted too
        # (discounts.spec.ts:87-96).
        # PRODUCTS.e2eProduct1 IS "Bean Juice" at pk 79, and populatedb creates
        # its own "Bean Juice" too -- two rows with that name make
        # `filter({hasText: "Bean Juice"})` ambiguous (SALEOR_32). The duplicate
        # is dropped in tier_cleanup. Price 3 is
        # PRODUCTS.productWithPriceLowerThan20.
        (79, "Bean Juice", None, 1241, "e2e", "57423879", 3),
        (115, "Black Hoodie", None, 297, "S", "BLACKHOODIE-S", 20),
        (85, "Colored Parrot Cushion", None, 982, "70 / 70", "PARROT-70", 25),
        (116, "Blue Hoodie 2", None, 301, "S", "BLUEHOODIE2-S", 20),
        (78, "Green Juice", None, 1242, "e2e", "GREENJUICE-E2E", 5),
        (64, "Ocean Poems", None, 1243, "ocean-poems-mp3", "ocean-poems-mp3", 22),
    ]
    usd = Channel.objects.filter(slug="default-channel")
    pln = Channel.objects.filter(slug="channel-pln")
    # SALEOR_46 adds the first channel to product 761; it starts unassigned.
    single_channel = {761: Channel.objects.none(), 763: pln, 764: usd}

    # PRODUCTS.e2eProduct1 is "Bean Juice" at pk 79, but populatedb already
    # created a "Bean Juice" of its own (which also owns the slug). The specs
    # match this product by name, so a second row makes
    # `filter({hasText: "Bean Juice"})` ambiguous (SALEOR_32). Drop it first, so
    # pk 79 can take both the name and the slug.
    Product.objects.filter(name="Bean Juice").exclude(pk=79).delete()

    # 672 ("Single product type") must keep has_variants=False for SALEOR_5's
    # no-variants flow, so any product that owns a variant is put on 671
    # ("Beer"), which does have variants.
    variants_type = ProductType.objects.get(pk=671)

    for pk, name, cat_pk, var_pk, var_name, sku, price in specs:
        product, _ = Product.objects.update_or_create(
            pk=pk,
            defaults={
                "name": name, "slug": slugify(name),
                "product_type": variants_type if var_pk else ptype,
                "category": Category.objects.filter(pk=cat_pk).first(),
            },
        )
        if var_pk:
            ProductVariant.objects.update_or_create(
                pk=var_pk,
                defaults={"product": product, "name": var_name,
                          "sku": sku or f"e2e-{var_pk}"},
            )
        channels = single_channel.get(pk)
        if channels is not None:
            ProductChannelListing.objects.filter(product=product).exclude(
                channel__in=channels
            ).delete()
        _publish_product(product, price, channels=channels)

    # SALEOR_62 bulk-deletes variants from PRODUCTS.multipleVariantsBulkDeleteProduct
    # (766), so it needs more than one.
    bulk_product = Product.objects.get(pk=766)
    for i, vpk in enumerate((1234, 1235), start=2):
        ProductVariant.objects.update_or_create(
            pk=vpk,
            defaults={"product": bulk_product, "name": f"bulk-{i}",
                      "sku": f"BULK-DEL-{i}"},
        )
    _publish_product(bulk_product, 10)

    # Referenced by name only.
    for name, cat_pk, price, sku in [
        ("beer to be updated", 507, None, None),
        ("a product to be deleted via bulk 1/3", None, None, None),
        ("a product to be deleted via bulk 2/3", None, None, None),
        ("a product to be deleted via bulk 3/3", None, None, None),
    ]:
        product, _ = Product.objects.update_or_create(
            slug=slugify(name),
            defaults={"name": name, "product_type": ptype,
                      "category": Category.objects.filter(pk=cat_pk).first()},
        )
        _publish_product(product, price)

    # navigation.spec.ts:38 expects "Polo Shirts"; populatedb_data.json:292
    # creates "Polo shirts". The snapshot evidently capitalised it, and nothing
    # in playwright/ refers to the lowercase spelling.
    Category.objects.filter(name="Polo shirts").update(name="Polo Shirts")

    # The variant edit page renders an `attribute-value` field per variant
    # attribute on the product's type. Without one, SALEOR_27/60 wait forever.
    from saleor.attribute.models import AttributeVariant

    size = Attribute.objects.filter(slug="size", type="product-type").first()
    if not size:
        size = Attribute.objects.filter(type="product-type").first()
    if size:
        for type_pk in {671, 672}:
            product_type = ProductType.objects.filter(pk=type_pk).first()
            if product_type and product_type.has_variants:
                AttributeVariant.objects.get_or_create(
                    attribute=size, product_type=product_type,
                    defaults={"sort_order": 0},
                )

    bump(Product)
    bump(ProductVariant)
    have = Product.objects.filter(pk__in=[s[0] for s in specs]).count()
    note(f"products: {have}/{len(specs)} by pk")


def tier_assigned_content():
    """SALEOR_189 / SALEOR_185 delete a type that HAS assigned objects -- the
    confirmation dialog only renders its consent checkbox
    (`delete-assigned-items-consent`) when something is assigned, so an empty
    type makes the test time out.
    """
    from saleor.page.models import Page

    page_type = PageType.objects.get(pk=35)  # "A page type to be removed"
    for i in (1, 2):
        title = f"e2e page assigned to removable page type {i}"
        Page.objects.update_or_create(
            slug=slugify(title),
            defaults={"title": title, "page_type": page_type, "is_published": True},
        )

    product_type = ProductType.objects.get(pk=699)  # "A product type to be removed"
    for i in (1, 2):
        name = f"e2e product assigned to removable product type {i}"
        product, _ = Product.objects.update_or_create(
            slug=slugify(name),
            defaults={"name": name, "product_type": product_type},
        )
        _publish_product(product)

    bump(Page)
    note(f"assigned content: {Page.objects.filter(page_type=page_type).count()} pages, "
         f"{Product.objects.filter(product_type=product_type).count()} products")


def _address(first, last, **kw):
    return Address.objects.create(
        first_name=first, last_name=last,
        company_name=kw.get("company", "Saleor"),
        street_address_1=kw.get("line1", "Teczowa"),
        street_address_2=kw.get("line2", "7"),
        city=kw.get("city", "WROCLAW"),
        postal_code=kw.get("zip", "53-601"),
        country=kw.get("country", "PL"),
        phone=kw.get("phone", "+48225042123"),
    )


def tier_users():
    """e2eTestData.ts:567-604 USERS and :721-780 CUSTOMERS.

    Passwords match populatedb's defaults so auth.setup.ts keeps working:
    staff use `password`, customers `password`.
    """
    # (pk, email, is_staff, is_active, first, last)
    specs = [
        (1347, "user-to-be-deactivated@gmai.com", False, True, "user", "to-be-deactivated"),
        (1349, "user-to-be-activated@gmai.com", False, False, "user", "to-be-activated"),
        (1371, "test123@hotmail.com", True, True, "e2e_staff_to_be_updated", "DO NOT DELETE"),
        (1372, "e2e-staff-to-be-deleted@saleor.io", True, True,
         "e2e_staff_to_be_deleted", "DO NOT DELETE"),
        (1364, "e2e-customer@activate.com", False, False, "e2e-customer", "to-be-activated"),
        (1365, "e2e-customer@deactivate.com", False, True, "e2e-customer", "to-be-deactivated"),
        (1366, "e2e_customer_with_addresses@saleor.io", False, True,
         "e2e_customer_with_addresses", "to-be-edited"),
        (1367, "e2e_customer@delete.com", False, True, "e2e_customer", "to-delete"),
    ]
    for pk, email, staff, active, first, last in specs:
        user, created = User.objects.update_or_create(
            pk=pk,
            defaults={"email": email, "is_staff": staff, "is_active": active,
                      "first_name": first, "last_name": last, "is_confirmed": True},
        )
        if created or not user.has_usable_password():
            user.set_password("password")
            user.save(update_fields=["password"])

    # Order creation selects this customer by email in RightSideDetailsPage.
    bump(User)
    order_customer, _ = User.objects.update_or_create(
        email="allison.freeman@example.com",
        defaults={"first_name": "Allison", "last_name": "Freeman",
                  "is_active": True, "is_staff": False, "is_confirmed": True},
    )
    order_customer.addresses.all().delete()
    order_address = _address("Allison", "Freeman")
    order_customer.addresses.add(order_address)
    order_customer.default_shipping_address = order_address
    order_customer.default_billing_address = order_address
    order_customer.save(update_fields=["default_shipping_address", "default_billing_address"])

    # CUSTOMERS.editCustomer (1366) includes two defaults and a third address
    # which SALEOR_209 selects as the new default billing address.
    editable = User.objects.get(pk=1366)
    editable.addresses.all().delete()
    ship = _address("e2e_customer_with_addresses", "to-be-edited")
    bill = _address("address", "to-be-deleted")
    additional = _address(
        "Test", "Test", company="", line1="Nowy Świat", line2="",
        city="WARSZAWA", zip="00-504", country="PL", phone="",
    )
    editable.addresses.add(ship, bill, additional)
    editable.default_shipping_address = ship
    editable.default_billing_address = bill
    editable.note = "simple note"
    editable.save(update_fields=[
        "default_shipping_address", "default_billing_address", "note",
    ])

    for i in (1, 2, 3):
        email = f"e2e_customer_{i}_bulk-delete@saleor.io"
        user, created = User.objects.update_or_create(
            email=email,
            defaults={"first_name": f"e2e_customer_{i}", "last_name": "bulk-delete",
                      "is_active": True, "is_confirmed": True},
        )
        if created:
            user.set_password("password")
            user.save(update_fields=["password"])

    for email, first, last in [
        ("user-for-password-reset@gmail.com", "e2e", "user"),
        ("change-password-user@gmail.com", "change password", "user"),
    ]:
        user, created = User.objects.update_or_create(
            email=email,
            defaults={"first_name": first, "last_name": last, "is_active": True,
                      "is_confirmed": True},
        )
        if created:
            user.set_password("password")
            user.save(update_fields=["password"])

    bump(User)
    bump(Address)
    note(f"users: {User.objects.filter(pk__in=[s[0] for s in specs]).count()}/{len(specs)} by pk")


def tier_permission_groups():
    """e2eTestData.ts:654-687 PERMISSION_GROUPS."""
    specs = [
        (110, "e2e_permission_group_to_be_deleted"),
        (111, "e2e_permission_group_to_be_updated"),
    ]
    for pk, name in specs:
        Group.objects.update_or_create(pk=pk, defaults={"name": name})

    members = [
        ("e2e_permission_group_member_1@grr.la", "e2e_permission_group_member_1", "test"),
        ("e2e_permission_group_member_2@grr.la", "e2e_permission_group_member_2", "test"),
        ("e2e_permission_group_member_3@grr.la", "e2e_permission_group_member_3", "test"),
    ]
    group = Group.objects.get(pk=111)
    group.user_set.clear()
    for email, first, last in members:
        user, created = User.objects.update_or_create(
            email=email,
            defaults={"first_name": first, "last_name": last, "is_staff": True,
                      "is_active": True, "is_confirmed": True},
        )
        if created:
            user.set_password("password")
            user.save(update_fields=["password"])
        group.user_set.add(user)

    # assignedPermissions: MANAGE_PRODUCTS, MANAGE_PLUGINS, MANAGE_STAFF
    group.permissions.set(
        Permission.objects.filter(
            codename__in=["manage_products", "manage_plugins", "manage_staff"]
        )
    )
    # SALEOR_212 assigns the staff member to "Channels Management"; populatedb's
    # create_staffs() derives group names from permission codenames and produces
    # "Channels management" (lowercase m). Same class of snapshot/populatedb
    # casing difference as "Polo Shirts" in tier_products.
    Group.objects.filter(name="Channels management").update(name="Channels Management")

    # USERS.staffToBeEdited retains its initial Apps management group in SALEOR_212.
    apps_group, _ = Group.objects.get_or_create(name="Apps management")
    apps_group.permissions.set(Permission.objects.filter(codename="manage_apps"))
    User.objects.get(pk=1371).groups.set([apps_group])

    bump(Group)
    note(f"permission groups: {Group.objects.filter(pk__in=[p for p, _ in specs]).count()}/2 by pk, "
         f"{group.user_set.count()} members")


def tier_gift_cards():
    """e2eTestData.ts:275-296 GIFT_CARDS. Tests locate cards by the last 4
    characters of the code, so the codes are built to end in those.
    """
    specs = [
        (53, "e2e-card-AD47"),
        (54, "e2e-card-7FF8"),
        (55, "e2e-card-F2DA"),
        (6, "e2e-card-d_10"),
    ]
    channel = Channel.objects.get(slug="default-channel")
    for pk, code in specs:
        GiftCard.objects.update_or_create(
            pk=pk,
            defaults={
                "code": code,
                "initial_balance_amount": Decimal("50"),
                "current_balance_amount": Decimal("50"),
                "currency": channel.currency_code,
                "is_active": pk != 54,  # 54 is "to be activated"
                # SALEOR_110 *toggles* "Gift card expires" and saves without
                # filling a date. Turning it ON with no date makes the API
                # reject the update with HTTP 400, so the card has to start
                # with an expiry date and the toggle clears it.
                "expiry_date": (timezone.now() + datetime.timedelta(days=365)).date(),
                # SALEOR_110 runs expandAndAddAllMetadata(), which assumes an
                # empty metadata section: leftovers from a previous run make its
                # `[name*='name']` locator match twice (strict mode violation).
                "metadata": {},
                "private_metadata": {},
            },
        )
    # giftCardsToBeDeleted has both `names` and `last4`: SALEOR_111 selects rows
    # by the names (which are gift card TAGS, the only free-text column in the
    # grid) and then asserts the codes ending in last4 are gone.
    from saleor.giftcard.models import GiftCardTag

    for name, last4 in [("to be deleted 1/2", "5EE6"), ("to be deleted 2/2", "9E39")]:
        card, _ = GiftCard.objects.update_or_create(
            code=f"e2e-del-{last4}",
            defaults={
                "initial_balance_amount": Decimal("50"),
                "current_balance_amount": Decimal("50"),
                "currency": channel.currency_code,
                "is_active": True,
            },
        )
        tag, _ = GiftCardTag.objects.get_or_create(name=name)
        card.tags.set([tag])
    bump(GiftCard)
    note(f"gift cards: {GiftCard.objects.filter(pk__in=[p for p, _ in specs]).count()}/4 by pk")


def tier_apps():
    """e2eTestData.ts:606-612 APPS.

    Also fixes singlePermissions/extensions.spec.ts SALEOR_10: the installed
    extensions list only renders its `extensions-installed` container when at
    least one app exists (InstalledExtensionsList.tsx:199 returns EmptyListState
    otherwise), so that test times out on an app-less database.
    """
    App.objects.update_or_create(
        pk=70,
        defaults={"name": "Saleor QA App", "is_active": True, "type": "local",
                  "identifier": "saleor-qa-app"},
    )
    bump(App)
    note(f"apps: {App.objects.filter(pk=70).count()}/1 by pk")


def tier_promotions():
    """e2eTestData.ts:76-182 DISCOUNTS. Promotion and PromotionRule use UUID pks.

    An Order-type promotion's rules need an order_predicate; a Catalogue one's
    need a catalogue_predicate. The dashboard refuses to render a rule whose
    predicate does not match its promotion type.
    """
    from saleor.discount.models import Promotion, PromotionRule

    usd = Channel.objects.get(slug="default-channel")
    pln = Channel.objects.filter(slug="channel-pln").first() or usd

    def catalogue_predicate():
        """A PRODUCT predicate, not a category one.

        SALEOR_166 opens a rule for editing and, when a condition row is
        present, picks PRODUCTS.e2eProductWithVariant1 ("Colored Parrot
        Cushion") from the value dropdown. That dropdown lists whatever the
        predicate type is, so a categoryPredicate makes it offer categories and
        the product is never found.
        """
        from saleor.graphql.core.utils import to_global_id_or_none

        # Deliberately NOT product 85 ("Colored Parrot Cushion"): the test
        # *selects* that one, and an already-selected value renders as a chip
        # rather than an option, so getByRole("option", ...) never matches it.
        product = Product.objects.filter(pk=763).first()
        if not product:
            return {}
        return {"productPredicate": {"ids": [to_global_id_or_none(product)]}}

    def order_predicate():
        # Base SALEOR_163 expects subtotal25 and a fixed-amount reward.
        # Equality avoids applying this editing fixture to unrelated order totals.
        return {
            "discountedObjectPredicate": {
                "baseSubtotalPrice": {"eq": "25"}
            }
        }

    # (encoded promotion id, name, type, [(encoded rule id, rule name, channel)])
    promos = [
        ("UHJvbW90aW9uOjI0MGVkZGVkLWYzMTAtNGUzZi1iNTlmLTFlMGFkYWE2ZWFkYg==",
         "e2e promotion to be edited", "catalogue", []),
        ("UHJvbW90aW9uOjRmNTQwMDc1LTZlZGMtNDI1NC1hY2U2LTQ2MzdlMGYxZWJhOA==",
         "e2e Order predicate promotion without rules", "order", []),
        ("UHJvbW90aW9uOmYyY2VjMDhkLTVkYmUtNGVjNC05NTNjLWMzMmQ5ZGQ2MTExYw==",
         "e2e Catalog promo with rules to be deleted", "catalogue", [
             ("UHJvbW90aW9uUnVsZTo3NDk4MGVhNS0zNDA2LTQxZGYtOTc3Mi1jMzg3MjNhMWEwOWM=", "rule 1", usd),
             ("UHJvbW90aW9uUnVsZTozMTEyMTE0Yy1hYjFkLTQ3OTktODY0My1jZDhlODMwYzllZmE=", "rule 2", usd),
             ("UHJvbW90aW9uUnVsZTozOWE3Zjc1Zi1jYTdmLTQ4ODgtOGE4NC02NzdjMTVhOGQ4Yjc=", "rule 3", usd),
         ]),
        ("UHJvbW90aW9uOjA1MDllZjhjLTc0ZTEtNGMyMC1iZDk5LWRhYWU1YWJlZDM1Nw==",
         "e2e Order promo with rules to be deleted", "order", [
             ("UHJvbW90aW9uUnVsZTo2ZTdlODNkOS1kNjJlLTQ2YmQtOGE2ZS03OTdlYTZiODk2NmQ=", "rule #1", usd),
             ("UHJvbW90aW9uUnVsZTo1MzQwNjEyYy0wOWJhLTQxYzUtYmY2Yy1lYmUzZTQ3MjY0MjY=", "rule #2", usd),
             ("UHJvbW90aW9uUnVsZTpjMzk5ZTM1Ni04OWFhLTQ0MTUtYWE0Zi01NThlZDQ2M2IwNTM=", "rule #3", usd),
         ]),
        ("UHJvbW90aW9uOjI0Njg3NmM5LWM1ZWMtNDBiYi1iMzExLWE3YWQ2YzBiZDc4NQ==",
         "e2e Order promo with rules to be updated", "order", [
             ("UHJvbW90aW9uUnVsZTo3NmEwOGYzZi0xMzZhLTRmNTUtYTc0NS1kZmIxNDZkOWI4ZGQ=", "rule 1", pln),
             ("UHJvbW90aW9uUnVsZTpjODIxMWJhNS05ZGRmLTRhYzQtOTdlMS04YmM0MzNhZjRlOTM=", "rule 2", pln),
         ]),
        ("UHJvbW90aW9uOmJkZTgyNGQ4LTk4ZTktNDM1NC04ODE4LTE1YzVjNmI2MWU2NQ==",
         "e2e Catalog promo with rules to be updated", "catalogue", [
             ("UHJvbW90aW9uUnVsZTplOWZjNjc2NS1kNzM2LTRhMzMtYjBiMy1hZWMxY2FmNGVkMDE=", "rule #1", usd),
             ("UHJvbW90aW9uUnVsZToyZjM3ZjRhOS01NjY0LTQzMDEtOWU4Zi0zZTliZGFjNmUyYjE=", "rule 2", usd),
         ]),
        ("UHJvbW90aW9uOjY0N2M2MzdhLTZjNTEtNDYxZC05MjQ2LTc0YTY0OGM0ZjAxNA==",
         "e2e Catalog predicate promotion with rules", "catalogue", []),
        ("UHJvbW90aW9uOjNmODZjZDAwLTUwNWEtNGVkNC04ZTliLTJmOGI4NGM3NGNlOQ==",
         "e2e Catalog promotion for adding rules", "catalogue", []),
        ("UHJvbW90aW9uOjJlM2VhNDkyLTRhMTAtNDYzOS05MWVmLTc1YzQ1OTUxNGQyMQ==",
         "e2e Order promotion for adding rules", "order", []),
    ]

    for enc_promo, name, ptype, rules in promos:
        promotion, _ = Promotion.objects.update_or_create(
            pk=uid(enc_promo),
            defaults={"name": name, "type": ptype,
                      "start_date": timezone.now() - datetime.timedelta(days=1),
                      # SALEOR_151 toggles the end date and asserts the input is
                      # gone, so it has to be set to begin with.
                      "end_date": timezone.now() + datetime.timedelta(days=30)},
        )
        # Rules the specs add get removed, so only the declared ones survive.
        promotion.rules.exclude(pk__in=[uid(r[0]) for r in rules]).delete()
        for enc_rule, rule_name, channel in rules:
            rule, _ = PromotionRule.objects.update_or_create(
                pk=uid(enc_rule),
                defaults={
                    "promotion": promotion, "name": rule_name,
                    "reward_value_type": "fixed" if ptype == "order" else "percentage",
                    "reward_value": Decimal("10"),
                    "catalogue_predicate": (
                        catalogue_predicate() if ptype == "catalogue" else {}
                    ),
                    "order_predicate": (
                        order_predicate() if ptype == "order" else {}
                    ),
                    "reward_type": "subtotal_discount" if ptype == "order" else None,
                },
            )
            rule.channels.set([channel])

    note(f"promotions: {Promotion.objects.filter(pk__in=[uid(p[0]) for p in promos]).count()}"
         f"/{len(promos)} by pk, {PromotionRule.objects.count()} rules")


def tier_vouchers():
    """e2eTestData.ts:52-75 VOUCHERS. A Voucher needs at least one VoucherCode
    (the dashboard lists vouchers by code) and a channel listing to be editable.
    """
    from saleor.discount.models import Voucher, VoucherChannelListing, VoucherCode

    # (pk, name)
    specs = [
        (202, "Free shipping voucher to be edited"),
        (203, "Usage limits voucher to be edited"),
        (204, "Minimum quantity voucher to be edited"),
        (206, "Delete voucher"),
        (209, "Assign category, product, collection"),
    ]
    for pk, name in specs:
        voucher, _ = Voucher.objects.update_or_create(
            pk=pk,
            defaults={"name": name, "type": "entire_order",
                      "discount_value_type": "fixed",
                      # SALEOR_87 sets these; reset so a re-run starts clean.
                      "usage_limit": None, "apply_once_per_customer": False,
                      "only_for_staff": False, "single_use": False,
                      "min_checkout_items_quantity": None},
        )
        VoucherCode.objects.update_or_create(
            voucher=voucher, defaults={"code": f"E2E-VOUCHER-{pk}"}
        )
        for channel in Channel.objects.all():
            VoucherChannelListing.objects.update_or_create(
                voucher=voucher, channel=channel,
                defaults={"discount_value": Decimal("10"),
                          "currency": channel.currency_code},
            )
        # SALEOR_94/95/96 assign a category, collection and product to 209 and
        # assert one row each afterwards, so it has to start unassigned.
        if pk == 209:
            voucher.categories.clear()
            voucher.collections.clear()
            voucher.products.clear()

    for i in (1, 2):
        name = f"Bulk delete voucher {i}/2"
        voucher, _ = Voucher.objects.update_or_create(
            name=name,
            defaults={"type": "entire_order", "discount_value_type": "fixed"},
        )
        VoucherCode.objects.update_or_create(
            voucher=voucher, defaults={"code": f"E2E-BULK-{i}"}
        )
        for channel in Channel.objects.all():
            VoucherChannelListing.objects.update_or_create(
                voucher=voucher, channel=channel,
                defaults={"discount_value": Decimal("10"),
                          "currency": channel.currency_code},
            )

    bump(Voucher)
    note(f"vouchers: {Voucher.objects.filter(pk__in=[p for p, _ in specs]).count()}"
         f"/{len(specs)} by pk")


def tier_translations():
    """e2eTestData.ts:614-630 TRANSLATIONS.

    The three targets (Category:512, Product:78, Collection:1) are created by
    other tiers; this only resets the translations the specs add or clear.
    """
    from saleor.discount.models import Voucher

    # Product 78 (Green Juice) comes from tier_products.

    # SALEOR_123 clears a translation on Collection:1, so one must exist; the
    # other two specs add translations, which must therefore be absent.
    from saleor.product.models import CollectionTranslation, ProductTranslation
    from saleor.product.models import CategoryTranslation

    # The specs navigate to PL_PL, which is the GraphQL enum for Django's
    # "pl-pl" (Polish (Poland)) -- NOT "pl" (Polish); core/languages.py lists
    # both, and populatedb writes "pl".
    def editorjs(*paragraphs):
        """Descriptions are editorjs documents; the dashboard renders each block
        back to back, which is why the specs' expected strings have no spaces
        between sentences."""
        return {
            "time": 0,
            "blocks": [
                {"id": f"b{i}", "type": "paragraph", "data": {"text": text}}
                for i, text in enumerate(paragraphs)
            ],
            "version": "2.24.3",
        }

    # SALEOR_123 asserts this exact description is on screen before clearing it.
    CollectionTranslation.objects.update_or_create(
        collection_id=1, language_code="pl-pl",
        defaults={
            "name": "Kolekcja letnia",
            # ONE block: SALEOR_123 calls translationRichText.clear(), whose
            # locator resolves one [contenteditable] per editorjs block, so
            # multiple blocks trigger a strict-mode violation. The expected
            # string runs the sentences together with no space after each
            # period, which is what a single block holds verbatim.
            "description": editorjs(
                "Letnia kolekcja Saleor obejmuje gamę produktów, które cieszą "
                "się popularnością na rynku.Sklep demonstracyjny na każdą porę "
                "roku.Saleor uchwycił słońce open source, e-commerce."
            ),
        },
    )

    # SALEOR_122 asserts the description starts with "Brukselka, szpinak", then
    # replaces it -- so the translation must exist up front.
    ProductTranslation.objects.update_or_create(
        product_id=78, language_code="pl-pl",
        defaults={
            "name": "Zielony Sok",
            "description": editorjs(
                "Brukselka, szpinak, groszek, jarmuż, sałata, kapusta, cukinia. "
                "Wszystkie warzywa, jakich będziesz potrzebować, w jednym pysznym soku."
            ),
        },
    )
    CategoryTranslation.objects.filter(category_id=512, language_code="pl-pl").delete()


    note(f"translations: product 78 ok, collection 1 has "
         f"{CollectionTranslation.objects.filter(collection_id=1).count()} translation(s)")


def tier_taxes():
    """taxes.spec.ts + CHANNELS.plnChannel (TaxConfiguration:1) and
    COUNTRIES.countryToBeAddedInTaxes.

    The taxes view lists channels via their TaxConfiguration, and populatedb
    only creates one per channel it made itself -- channels added here would not
    appear at all (SALEOR_116 waits for "a channel for tax tests").
    typeAllTaxRatesForCountry() fills six rate inputs, i.e. one per tax class,
    so six classes must exist.
    """
    from saleor.tax.models import (
        TaxClass,
        TaxClassCountryRate,
        TaxConfiguration,
        TaxConfigurationPerCountry,
    )

    for channel in Channel.objects.all():
        TaxConfiguration.objects.update_or_create(
            channel=channel,
            defaults={"charge_taxes": True, "tax_calculation_strategy": "FLAT_RATES",
                      "display_gross_prices": True, "prices_entered_with_tax": True},
        )

    # SALEOR_117 fills a rate per tax class and locates each input by the class
    # name (taxesPage.ts:43-55), so the names must match exactly -- including
    # the trailing space on the data-services one. populatedb's
    # create_tax_classes() only makes "Groceries" and "Books".
    names = [
        "No Taxes",
        "Audio Products (tapes, cds etc.)",
        "Data services - storage and retrieval ",
        "standard",
        "Temporary Unmapped Other SKU - taxable default",
    ]
    for name in names:
        tax_class, _ = TaxClass.objects.get_or_create(name=name)
        # Rates for the countries the specs touch; the Countries tab renders
        # nothing without at least one rate row.
        for country, rate in [("PL", 23), ("US", 10), ("DE", 19)]:
            TaxClassCountryRate.objects.update_or_create(
                tax_class=tax_class, country=country,
                defaults={"rate": Decimal(rate)},
            )

    # These specs ADD things, and the pickers hide what already exists, so a
    # re-run needs the previous run's additions removed:
    #   SALEOR_116 adds a Canada country exception to a channel
    #   SALEOR_117 adds "Bosnia and Herzegovina" (BA) as a taxed country
    #   SALEOR_118 creates the tax class "Automation test tax class"
    TaxConfigurationPerCountry.objects.filter(country="CA").delete()
    TaxClassCountryRate.objects.filter(country="BA").delete()
    TaxClass.objects.filter(
        name__in=["Automation test tax class", "New tax class"]
    ).delete()

    # Drop classes this seeder created under earlier, wrong names.
    TaxClass.objects.filter(
        name__in=["Standard", "Electronics", "Clothing", "Services"]
    ).delete()

    note(f"taxes: {TaxConfiguration.objects.count()} configs, "
         f"{TaxClass.objects.count()} classes, {TaxClassCountryRate.objects.count()} rates")


def tier_cleanup():
    """Remove artifacts the tests themselves create.

    Several specs create objects with FIXED identifiers, so they only pass on a
    database where those do not exist yet:

    * SALEOR_211/212 invite staff at test.staff.john.create@example.com and
      test.staff.john.edit@example.com -- a re-run hits the unique email
      constraint, the mutation errors and no success banner appears.
    * SALEOR_105 issues a gift card, then looks for it in the grid, which is
      paginated; cards accumulated by earlier runs push it off the first page.

    Run last, so it also clears anything the current seed pass duplicated.
    """
    from saleor.giftcard.models import GiftCardTag

    n_users = User.objects.filter(email__startswith="test.staff.john.").delete()[0]

    # variantsPage.typeSku() defaults to the fixed SKU "sku dummy e2e"
    # (variantsPage.ts:95), so SALEOR_27 creating a variant fails on the second
    # run with "Product variant with this Sku already exists."
    n_var = ProductVariant.objects.filter(sku="sku dummy e2e").delete()[0]

    # SALEOR_46 uploads media to PRODUCTS.singleProductTypeToBeUpdated (761) and
    # locates `product-image` afterwards; images pile up across runs until the
    # locator matches many elements (strict-mode violation).
    from saleor.product.models import ProductMedia

    n_media = ProductMedia.objects.filter(product_id=761).delete()[0]

    # Cards issued by SALEOR_105 carry this tag verbatim.
    junk_tags = GiftCardTag.objects.filter(
        name__in=["super ultra automation discount", "e2e-automation"]
    )
    n_cards = GiftCard.objects.filter(tags__in=junk_tags).distinct().delete()[0]
    junk_tags.delete()

    n_wh = Warehouse.objects.filter(name__startswith="e2e test - warehouse").delete()[0]

    # Channel.orders is PROTECT, and the order specs create orders in the
    # channels the channel specs leave behind, so those orders go first.
    from saleor.order.models import Order

    junk_channels = Channel.objects.filter(name="z - automation")
    Order.objects.filter(channel__in=junk_channels).delete()
    n_ch = junk_channels.delete()[0]

    # SALEOR_105/111 locate cards in a paginated grid (20 rows). populatedb's
    # demo cards (code "Gift_card_N") push the e2e fixtures past the first page,
    # so the tests never see them. Nothing in e2eTestData.ts refers to the demo
    # cards -- only ids 53/54/55/6 and the four last4 codes -- so they go.
    n_demo = GiftCard.objects.filter(code__startswith="Gift_card_").delete()[0]

    n_dup = 0  # handled in tier_products, before pk 79 is created

    # Saleor's product list search reads product_product.search_vector, which is
    # only populated by the API's own save paths -- rows written straight through
    # the ORM leave it NULL and are unsearchable (SALEOR_57 searches for
    # "beer with variants" and gets an empty grid).
    from saleor.product.search import update_products_search_vector

    stale = list(
        Product.objects.filter(search_vector__isnull=True).values_list("pk", flat=True)
    )
    if stale:
        update_products_search_vector(stale)
    note(f"search vectors rebuilt: {len(stale)} products")

    # taxes / giftCards / collections / categories specs call
    # metadataSeoPage.expandAndAddAllMetadata(), whose `[name*='name']` locator
    # assumes the metadata section starts empty -- a second run otherwise dies
    # with a strict-mode violation on 2 matching inputs.
    blank = {"metadata": {}, "private_metadata": {}}
    Category.objects.filter(pk__in=[507, 511, 512]).update(**blank)
    Collection.objects.filter(pk__in=[1, 166, 167]).update(**blank)
    GiftCard.objects.filter(pk__in=[53, 54, 55, 6]).update(**blank)

    note(f"cleanup: {n_users} staff, {n_cards} gift cards, {n_demo} demo cards, "
         f"{n_dup} dup products, {n_var} variants, {n_media} media, {n_wh} warehouses, "
         f"{n_ch} channels, metadata reset")


def tier_shipping():
    """e2eTestData.ts:523-566 SHIPPING_METHODS. `id` is a ShippingZone."""
    specs = [
        (2389, "e2e-test-shippingZone-to-be-deleted"),
        (2390, "Shipping method that is used to add rates"),
        (2392, "e2e-test-shippingZone-to-be-updated"),
        (2393, "e2e-test-shippingZone-to-be-bulk-deleted-1"),
        (2394, "e2e-test-shippingZone-to-be-bulk-deleted-2"),
        (2395, "e2e-test-shippingZone-to-be-bulk-deleted-3"),
    ]
    for pk, name in specs:
        zone, _ = ShippingZone.objects.update_or_create(
            pk=pk, defaults={"name": name, "countries": ["PL", "US"]}
        )
        # One channel only: the shipping-rate form renders a price/min/max input
        # per channel the zone belongs to, and SALEOR_32/33 fill them by test-id,
        # so several channels make those locators ambiguous (strict violation).
        zone.channels.set(Channel.objects.filter(slug="default-channel"))

    # SALEOR_37 reads the zone's already-assigned warehouses (Oceania, Africa)
    # and then assigns Americas and Europe, so the first two must be there and
    # the last two must not.
    zone_to_update = ShippingZone.objects.get(pk=2392)
    zone_to_update.warehouses.set(
        Warehouse.objects.filter(name__in=["Oceania", "Africa"])
    )

    # ShippingMethodType:2220 -- the rates the delete test removes from
    # zone 2389.
    zone = ShippingZone.objects.get(pk=2389)
    ShippingMethod.objects.update_or_create(
        pk=2220,
        defaults={"name": "shippingMEthod_to-be-deleted", "type": "price",
                  "shipping_zone": zone},
    )
    ShippingMethod.objects.update_or_create(
        name="shippingMethod_to_be_deleted",
        shipping_zone=zone,
        defaults={"type": "weight"},
    )
    bump(ShippingZone)
    bump(ShippingMethod)
    note(f"shipping zones: {ShippingZone.objects.filter(pk__in=[p for p, _ in specs]).count()}/6 by pk")


def tier_order_promotions():
    """Initial promotion data required by SALEOR_215 and SALEOR_216."""
    from saleor.discount.models import Promotion, PromotionRule
    from saleor.product.utils.variants import fetch_variants_for_promotion_rules
    from saleor.product.utils.variant_prices import update_discounted_prices_for_promotion
    import base64

    specs = [
        ("catalogue", "channel-pln", 40,
         {"productPredicate": {"ids": [base64.b64encode(b"Product:770").decode()]}}),
        ("order", "e2e-channel-do-not-delete", 5,
         {"discountedObjectPredicate": {"baseSubtotalPrice": {"range": {"gte": "20"}}}}),
    ]
    for kind, slug, percent, predicate in specs:
        key = f"saleor-e2e-order-discount-{kind}"
        promotion, _ = Promotion.objects.update_or_create(
            pk=uuid.uuid5(uuid.NAMESPACE_URL, key),
            defaults={"name": key, "type": kind,
                      "start_date": timezone.now() - datetime.timedelta(days=1),
                      "end_date": None},
        )
        rule, _ = PromotionRule.objects.update_or_create(
            pk=uuid.uuid5(uuid.NAMESPACE_URL, key + "-rule"),
            defaults={"promotion": promotion, "name": key,
                      "reward_value_type": "percentage", "reward_value": percent,
                      "reward_type": "subtotal_discount" if kind == "order" else None,
                      "catalogue_predicate": predicate if kind == "catalogue" else {},
                      "order_predicate": predicate if kind == "order" else {}},
        )
        rule.channels.set([Channel.objects.get(slug=slug)])
        if kind == "catalogue":
            fetch_variants_for_promotion_rules(PromotionRule.objects.filter(pk=rule.pk))
    update_discounted_prices_for_promotion(Product.objects.filter(pk=770))
    note("order promotions: PLN product770 40%; dedicated order channel subtotal20+ 5%")


def tier_user_search():
    """Refresh ORM-seeded users using the running application's search schema."""
    fields = {field.name for field in User._meta.fields}
    if "search_vector" in fields:
        from saleor.account.search import update_user_search_vector
        for user in User.objects.prefetch_related("addresses").all():
            update_user_search_vector(user)
    else:
        from saleor.account.search import prepare_user_search_document_value
        for user in User.objects.prefetch_related("addresses").all():
            user.search_document = prepare_user_search_document_value(
                user, already_prefetched=True
            )
            user.save(update_fields=["search_document"])
    note(f"user search: rebuilt {User.objects.count()} users")


def tier_orders():
    """Initial states for active orders.spec.ts cases, using the pinned fixture IDs."""
    from saleor.order import OrderChargeStatus, OrderOrigin
    from saleor.order.models import Order, OrderLine
    from saleor.payment.models import TransactionItem
    from saleor.shipping.models import ShippingMethodChannelListing
    from saleor.warehouse.models import Allocation, ChannelWarehouse, Stock

    normal = Channel.objects.get(slug="default-channel")
    transaction_channel = Channel.objects.get(slug="transaction-flow-channel")
    pln = Channel.objects.get(slug="channel-pln")
    warehouse = Warehouse.objects.get(name="Europe")
    zone, _ = ShippingZone.objects.update_or_create(
        name="e2e order shipping", defaults={"countries": ["PL", "US", "GB"]}
    )
    channels = [normal, transaction_channel, pln,
                Channel.objects.get(slug="e2e-channel-do-not-delete")]
    zone.channels.set(channels)
    zone.warehouses.set([warehouse])
    method, _ = ShippingMethod.objects.update_or_create(
        shipping_zone=zone, name="e2e order delivery", defaults={"type": "price"}
    )
    for channel in channels:
        ChannelWarehouse.objects.get_or_create(
            channel=channel, warehouse=warehouse, defaults={"sort_order": 0}
        )
        ShippingMethodChannelListing.objects.update_or_create(
            shipping_method=method, channel=channel,
            defaults={"currency": channel.currency_code, "price_amount": 0,
                      "minimum_order_price_amount": 0},
        )
    # Draft product search requests IN_STOCK, including discount test products.
    for variant_id in [1239, 1241, 1243]:
        Stock.objects.update_or_create(
            warehouse=warehouse, product_variant_id=variant_id,
            defaults={"quantity": 1000},
        )
    customer = User.objects.get(pk=1366)
    # UUIDs decode directly from ORDERS.* in playwright/data/e2eTestData.ts.
    specs = [
        ("018ec44e-5800-44c4-9b30-d17a21b9c983", transaction_channel, "unfulfilled", 1240, 1, 10, False, True, None),
        ("2a553d39-9e49-4ea9-b271-796eb98ba773", transaction_channel, "unfulfilled", 1240, 12, 10, False, True, None),
        ("c86d33ba-109b-4352-93ab-99c0a7f98da9", normal, "unfulfilled", 1240, 1, 10, False, True, None),
        ("3cdaa84b-7816-4eb6-a50c-814769ac4110", normal, "fulfilled", 1240, 1, 10, True, True, None),
        ("02348f29-72b8-4e0d-b586-ce7960d24cd4", normal, "fulfilled", 1240, 1, 10, True, True, None),
        ("eaaf0438-792b-4e7e-b285-10d25b23434d", normal, "unfulfilled", 1240, 1, 10, False, True, None),
        ("f845977a-3f7c-4467-b77c-d64f8a0562d2", pln, "draft", 297, 1, 20, False, True, None),
        ("03823843-b873-4e46-a552-674db0f16dfa", normal, "unfulfilled", 1240, 1, 10, False, False, None),
        (str(uuid.uuid5(uuid.NAMESPACE_URL, "saleor-e2e-draft-3265")), normal, "draft", 1240, 1, 10, False, True, 3265),
        (str(uuid.uuid5(uuid.NAMESPACE_URL, "saleor-e2e-draft-3266")), normal, "draft", 1240, 1, 10, False, True, 3266),
    ]
    fixture_ids = [row[0] for row in specs]
    TransactionItem.objects.filter(order_id__in=fixture_ids).delete()
    Order.objects.filter(pk__in=fixture_ids).delete()
    for pk, channel, status, variant_id, quantity, unit, paid, has_customer, number in specs:
        variant = ProductVariant.objects.get(pk=variant_id)
        stock, _ = Stock.objects.update_or_create(
            warehouse=warehouse, product_variant=variant, defaults={"quantity": 1000}
        )
        _publish_product(variant.product, unit, channels=[channel])
        total = Decimal(unit) * quantity
        order = Order.objects.create(
            pk=pk, channel=channel, currency=channel.currency_code, status=status,
            origin=OrderOrigin.DRAFT, user=customer if has_customer else None,
            user_email=customer.email if has_customer else "",
            billing_address=customer.default_billing_address.get_copy(),
            shipping_address=customer.default_shipping_address.get_copy(),
            shipping_method=method, shipping_method_name=method.name,
            total_net_amount=total, total_gross_amount=total,
            undiscounted_total_net_amount=total, undiscounted_total_gross_amount=total,
            subtotal_net_amount=total, subtotal_gross_amount=total,
            total_charged_amount=total if paid else 0,
            charge_status=OrderChargeStatus.FULL if paid else OrderChargeStatus.NONE,
            should_refresh_prices=False, lines_count=1,
            **({"number": number} if number else {}),
        )
        line = OrderLine.objects.create(
            order=order, variant=variant, product_name=variant.product.name,
            variant_name=variant.name, product_sku=variant.sku,
            product_type_id=variant.product.product_type_id,
            is_shipping_required=True, is_gift_card=False,
            quantity=quantity, quantity_fulfilled=quantity if status == "fulfilled" else 0,
            currency=channel.currency_code,
            unit_price_net_amount=unit, unit_price_gross_amount=unit,
            total_price_net_amount=total, total_price_gross_amount=total,
            undiscounted_unit_price_net_amount=unit, undiscounted_unit_price_gross_amount=unit,
            undiscounted_total_price_net_amount=total, undiscounted_total_price_gross_amount=total,
            base_unit_price_amount=unit, undiscounted_base_unit_price_amount=unit,
            tax_rate=0,
        )
        if paid:
            TransactionItem.objects.create(order=order, name="Seeded manual payment",
                currency=channel.currency_code, charged_value=total)
        if status == "fulfilled":
            fulfillment = order.fulfillments.create()
            fulfillment.lines.create(order_line=line, quantity=quantity, stock=stock)
        elif status == "unfulfilled":
            Allocation.objects.create(order_line=line, stock=stock, quantity_allocated=quantity)
    with connection.cursor() as cursor:
        cursor.execute("SELECT setval('order_order_number_seq', (SELECT MAX(number) FROM order_order))")
    note(f"orders: {len(specs)} active-case fixtures, with stock, shipping and payment state")


# Dependency order: leaves first, then things that reference them.
TIERS = [
    ("attributes", tier_attributes),
    ("page-types", tier_page_types),
    ("product-types", tier_product_types),
    ("categories", tier_categories),
    ("collections", tier_collections),
    ("channels", tier_channels),
    ("menus", tier_menus),
    ("warehouses", tier_warehouses),
    ("shipping", tier_shipping),
    ("products", tier_products),
    ("assigned-content", tier_assigned_content),
    ("users", tier_users),
    ("permission-groups", tier_permission_groups),
    ("gift-cards", tier_gift_cards),
    ("apps", tier_apps),
    ("promotions", tier_promotions),
    ("vouchers", tier_vouchers),
    ("translations", tier_translations),
    ("taxes", tier_taxes),
    ("orders", tier_orders),
    ("order-promotions", tier_order_promotions),
    ("user-search", tier_user_search),
    ("cleanup", tier_cleanup),   # must stay last
]

if __name__ == "__main__":
    names = [n for n, _ in TIERS]
    wanted = sys.argv[1:] or names
    unknown = [w for w in wanted if w not in names]
    if unknown:
        sys.exit(f"unknown tier(s): {', '.join(unknown)}\nknown: {', '.join(names)}")
    lookup = dict(TIERS)
    for name in wanted:
        print(f"--- {name} ---")
        lookup[name]()
    print(f"\nseeded {len(wanted)} tier(s)")
