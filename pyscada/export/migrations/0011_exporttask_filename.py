# -*- coding: utf-8 -*-
# Generated by Django 1.10.2 on 2017-04-06 10:24
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('export', '0010_auto_20161128_1049'),
    ]

    operations = [
        migrations.AddField(
            model_name='exporttask',
            name='filename',
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
    ]
