from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_add_ops_roles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                default="seller",
                max_length=20,
                choices=[
                    ("admin", "Admin"),
                    ("lead_manager", "Lead Manager"),
                    ("retail_head", "Retail Head"),
                    ("sales_head", "Sales Head"),
                    ("retail", "Retail Associate"),
                    ("sales", "Sales Associate"),
                    ("inspector", "Inspection Associate"),
                    ("procurement", "Procurement Associate"),
                    ("seller", "Seller"),
                    ("dealer", "Dealer/Buyer"),
                ],
            ),
        ),
    ]
