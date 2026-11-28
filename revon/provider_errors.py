"""Classify provider refusals without retaining their diagnostic text."""
import json


HINTS = {
    'permission': '无调用权限。请核对当前密钥的授权范围、套餐和模型。',
    'unlicensed_model': '无调用权限。当前套餐未开通所请求的模型，请核对订阅权益或切换模型。',
    'balance': '模型服务商报告余额或可用额度不足。请查看账单、额度或重置时间。',
    'billing': '账号因计费状态已暂停。请在供应商控制台查看账单。',
    'subscription': '订阅未生效或已过期。请检查套餐状态以及对应的密钥和接口地址。',
    'authentication': '密钥无效或已过期。请核对密钥和接口地址。',
    'rate_limit': '请求频率受限。请稍后再试。',
}


def provider_error_kind(status=None, detail=None):
    if isinstance(detail, bytes):
        detail = detail.decode('utf-8', errors='replace')
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except (ValueError, RecursionError):
            pass
    if isinstance(detail, dict):
        detail = detail.get('error', detail)
    if isinstance(detail, dict):
        codes = {str(detail.get(k, '')).lower() for k in ('code', 'type')}
        message = str(detail.get('message') or '').lower()
    else:
        codes, message = set(), str(detail or '').lower()
    if 'accessdenied.unpurchased' in codes:
        return 'unlicensed_model'
    if 'account_billing_suspended' in codes:
        return 'billing'
    if 'invalidsubscription' in codes:
        return 'subscription'
    if status == 402 or codes & {'insufficient_quota', 'insufficient_balance', 'billing_hard_limit_reached',
                                  'arrearage', '1113'} or any(s in message for s in (
            'credit balance is too low', 'insufficient credits', 'insufficient balance', '余额不足')):
        return 'balance'
    if status == 401:
        return 'authentication'
    if status == 403 or codes & {'access_denied', 'permission_denied'}:
        return 'permission'
    if status == 429 and (codes & {'rate_limit_exceeded', 'rate_limit_error'} or 'rate limit' in message):
        return 'rate_limit'
    return ''
