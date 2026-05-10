from rest_framework import serializers
from .models import RuleConfig, RuleVersionHistory


class RuleConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleConfig
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class RuleVersionHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleVersionHistory
        fields = '__all__'
        read_only_fields = ('created_at',)


class DecisionRequestSerializer(serializers.Serializer):
    rule_id = serializers.CharField(max_length=100)
    context = serializers.DictField()


class DecisionResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    result = serializers.DictField(required=False)
    error = serializers.CharField(required=False)


class RuleSaveRequestSerializer(serializers.Serializer):
    rule_id = serializers.CharField(max_length=100)
    rule_name = serializers.CharField(max_length=200)
    rule_type = serializers.CharField(max_length=30)
    engine_type = serializers.CharField(max_length=20, required=False, default='simpleeval')
    rule_content = serializers.DictField(required=False)
    business_id = serializers.CharField(required=False, allow_blank=True)
    business_group = serializers.CharField(required=False, allow_blank=True)
    category_key = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(default=True)
    created_by = serializers.CharField(required=False, allow_blank=True)