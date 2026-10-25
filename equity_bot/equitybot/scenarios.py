"""Deterministic company-equity value scenarios from sourced assumptions only."""
from .metrics import finite

def calculate(model,a):
    def get(k):
        v=a[k]
        if not finite(v): raise ValueError('场景参数必须有限数字')
        return v
    if model=='stable':
        profit=get('normalized_net_income'); multiple=get('justified_pe')
        if profit<=0 or multiple<=0: raise ValueError('正常化盈利或倍数无效')
        return profit*multiple
    if model=='growth':
        flows=a['fcff']; rate=get('discount_rate'); g=get('terminal_growth')
        if not flows or not all(finite(x) for x in flows) or rate<=g or rate<=0 or g<=-1: raise ValueError('DCF参数无效')
        pv=sum(x/(1+rate)**(i+1) for i,x in enumerate(flows))
        terminal=flows[-1]*(1+g)/(rate-g)/(1+rate)**len(flows)
        return pv+terminal+get('cash')-get('debt')-get('other_claims')
    if model=='cyclical':
        # Resource scenario: commodity USD/unit, units/year, royalty fraction, all costs USD.
        revenue=get('commodity_price')*get('production')
        operating=revenue*(1-get('royalty_rate'))-get('unit_cash_cost')*get('production')-get('fixed_costs')
        fcff=operating*(1-get('tax_rate'))-get('maintenance_capex')-get('growth_capex')-get('working_capital_increase')
        rate=get('discount_rate'); g=get('terminal_growth')
        if rate<=g or not 0<=get('tax_rate')<1 or not 0<=get('royalty_rate')<1: raise ValueError('资源场景无效')
        # Explicit constant cash-flow scenario, country risk is in discount rate assumptions.
        return fcff/(rate-g)+get('cash')-get('debt')-get('other_claims')
    if model=='conglomerate':
        segments=a['segments']
        if not segments or not all(finite(s['enterprise_value']) for s in segments): raise ValueError('分部价值不完整')
        return sum(s['enterprise_value'] for s in segments)+get('cash')-get('debt')-get('holding_cost_value')-get('other_claims')
    raise ValueError('模型暂不覆盖')
