from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import ContainerTransaction, Inventory_List

@receiver(post_save, sender=ContainerTransaction)
def update_inventory_on_transaction(sender, instance, created, **kwargs):
    if created:
        try:
            inventory_item = Inventory_List.objects.get(container=instance.container, product_name__iexact=instance.product)
        except Inventory_List.DoesNotExist:
            try:
                inventory_item = Inventory_List.objects.filter(container=instance.container).first()
            except Inventory_List.DoesNotExist:
                inventory_item = None

        if not inventory_item:
            raise ValidationError("Inventory item for the container not found.")

        if instance.sale_status in ("sold_to_company", "sold_to_customer"):
            qty = getattr(instance, "quantity", None) or Decimal("0")

            inventory_item.in_stock_qty = inventory_item.in_stock_qty - qty
            if inventory_item.in_stock_qty < 0:
                inventory_item.in_stock_qty = Decimal("0.00")

            inventory_item.total_sold_qty = (inventory_item.total_sold_qty or Decimal("0")) + qty
            inventory_item.total_sold_count = (inventory_item.total_sold_count or 0) + 1

            if instance.total_price and qty:
                inventory_item.sold_price = (Decimal(instance.total_price) / qty).quantize(Decimal("0.01"))
            inventory_item.save()

@receiver(post_delete, sender=ContainerTransaction)
def rollback_inventory_on_transaction_delete(sender, instance, **kwargs):

    try:
        inventory_item = Inventory_List.objects.get(container=instance.container, product_name__iexact=instance.product)
    except Inventory_List.DoesNotExist:
        inventory_item = Inventory_List.objects.filter(container=instance.container).first()

    if not inventory_item:
        return

    if instance.sale_status in ("sold_to_company", "sold_to_customer"):
        qty = getattr(instance, "quantity", None) or Decimal("0")
        inventory_item.in_stock_qty = inventory_item.in_stock_qty + qty
        inventory_item.total_sold_qty = max(inventory_item.total_sold_qty - qty, Decimal("0"))
        inventory_item.total_sold_count = max(inventory_item.total_sold_count - 1, 0)
        inventory_item.save()
