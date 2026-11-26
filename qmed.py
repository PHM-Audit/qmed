# -*- coding: utf-8 -*-
# QMed v0.3 — 统一医疗判定引擎 (QThink-Med用药判定 × MedCheck越界判定)
# 知识源: 公开OTC/说明书口径+公开临床常识, 保守取值; 三态出口; 不编造纪律
# 路由: AI输出(长文/计划/安抚语气) -> MedCheck B1-B5越界判定
#       用户提问(口语/药物+联用) -> 用药安全判定
#       都不是 -> UNKNOWN如实拒答
import re, sys, os

__version__ = "0.3.0"

# ==================== 药物词表 v0.3 (俗名/品牌/通用名 → 类目) ====================
DRUGS = {
  # 解热镇痛
  'acetaminophen': ['对乙酰氨基酚','扑热息痛','泰诺林','必理通','退烧药','止痛片','散利痛'],
  'ibuprofen': ['布洛芬','美林','芬必得'],
  'aspirin': ['阿司匹林','拜阿司匹灵',' aspirin '],
  'nsaid_other': ['双氯芬酸','扶他林','塞来昔布','西乐葆','依托考昔','消炎痛','吲哚美辛'],
  # 抗生素/抗感染
  'cephalosporin': ['头孢','先锋','头包'],
  'compound_cold': ['感冒药','泰诺','白加黑','感康','快克','新康泰克','康泰克','999感冒灵','日夜百服咛','小儿氨酚黄那敏'],
  'penicillin': ['阿莫西林','青霉素','克拉维酸','阿莫克拉'],
  'nitroimidazole': ['甲硝唑','替硝唑','奥硝唑'],
  'quinolone': ['左氧氟沙星','莫西沙星','环丙沙星','诺氟沙星','氟哌酸','氧氟沙星'],
  'macrolide': ['阿奇霉素','红霉素','克拉霉素','罗红霉素'],
  'tetracycline': ['多西环素','米诺环素','四环素'],
  # 心血管
  'statin': ['他汀','阿托伐他汀','立普妥','瑞舒伐他汀','可定','辛伐他汀','洛伐他汀'],
  'ccb': ['氨氯地平','络活喜','硝苯地平','拜新同','非洛地平','地尔硫卓'],
  'beta_blocker': ['美托洛尔','倍他乐克','比索洛尔','普萘洛尔','心得安'],
  'warfarin': ['华法林','可密定','抗凝药'],
  'antiplatelet': ['氯吡格雷','波立维','替格瑞洛'],
  # 降糖
  'metformin': ['二甲双胍','格华止'],
  'sulfonylurea': ['格列美脲','格列齐特','格列本脲','优降糖','达美康'],
  'insulin': ['胰岛素','诺和灵','甘精胰岛素','来得时'],
  # 精神/神经
  'benzo': ['地西泮','安定','阿普唑仑','佳乐定','劳拉西泮','氯硝西泮','唑吡坦','思诺思','佐匹克隆','安眠药'],
  'ssri': ['舍曲林','氟西汀','百忧解','帕罗西汀','赛乐特','艾司西酞普兰','来士普','西酞普兰','文拉法辛','抗抑郁药'],
  'antiepileptic': ['拉莫三嗪','利必通','丙戊酸','德巴金','卡马西平','得理多','左乙拉西坦','开浦兰'],
  # 消化
  'ppi': ['奥美拉唑','洛赛克','雷贝拉唑','泮托拉唑','埃索美拉唑','耐信','胃药'],
  'iron': ['铁剂','硫酸亚铁','琥珀酸亚铁','多糖铁'],
  # 抗过敏
  'antihistamine': ['氯雷他定','开瑞坦','西替利嗪','仙特明','扑尔敏','氯苯那敏'],
}
# 逆向: 口语类别词(大众把抗生素叫消炎药)
COLLOQUIAL = {'消炎药': ['cephalosporin','penicillin','quinolone','macrolide','nitroimidazole'],
              '降压药': ['ccb','beta_blocker'], '降糖药': ['metformin','sulfonylurea','insulin'],
              '止痛药': ['acetaminophen','ibuprofen','nsaid_other']}
SR_FORM = ['缓释','控释','肠溶','缓释胶囊','控释片','肠溶片','肠溶胶囊']
NEG_WORDS = ['没','不','未','无','停','戒']
def has(t, pool): return any(k in t for k in pool)
def find_drugs(t):
    t = t.lower(); out = {}
    for cls, pool in DRUGS.items():
        hits = [k for k in pool if k in t]
        if hits: out.setdefault(cls, []).extend(hits)
    for cw, clss in COLLOQUIAL.items():
        if cw in t:
            for c in clss: out.setdefault(c, []).append(cw)
    return out
def alcohols(t): return has(t, ['酒','啤酒','白酒','红酒','喝酒','含酒精','酗'])
def grapefruit(t): return has(t, ['西柚','葡萄柚','柚子'])
def caffeine(t): return has(t, ['咖啡','浓茶','奶茶','红牛','功能饮料'])

# ==================== 禁忌对表 v0.3 (公开说明书/临床常识口径) ====================
def interaction_rules(t, drugs):
    vols = []
    cls = set(drugs.keys())
    # 双硫仑: 头孢/硝基咪唑 × 酒精
    if alcohols(t) and cls & {'cephalosporin','nitroimidazole'}:
        vols.append(('qmed_disulfiram','VETO','头孢/甲硝唑类与酒精可引发双硫仑样反应(公开临床常识), 严重可危及生命: 用药期间及停药后至少7天内禁酒'))
    # 酒精×安眠药 呼吸抑制
    if alcohols(t) and cls & {'benzo'}:
        vols.append(('qmed_alc_sedative','VETO','酒精与安眠/镇静类药物同用会加重中枢抑制(公开说明书口径), 可致呼吸抑制, 严禁同服'))
    # 酒精×对乙酰氨基酚 肝毒性
    if alcohols(t) and cls & {'acetaminophen'}:
        vols.append(('qmed_alc_aceta','VETO','酒精与对乙酰氨基酚叠加肝毒性(公开说明书口径), 饮酒期间勿服, 长期饮酒者日上限更低'))
    # 西柚×他汀/CCB (CYP3A4)
    if grapefruit(t) and cls & {'statin','ccb'}:
        vols.append(('qmed_grapefruit','VETO','西柚/葡萄柚抑制CYP3A4代谢(公开临床常识), 与他汀或地平类降压药同服可使血药浓度异常升高。服药期间避免西柚及其果汁'))
    # 阿司匹林×布洛芬 (拮抗抗血小板)
    if cls & {'aspirin'} and cls & {'ibuprofen'}:
        vols.append(('qmed_asa_ibu','VETO','布洛芬会拮抗阿司匹林的抗血小板作用(公开临床常识), 两药不宜同服; 如在服阿司匹林, 止痛/退热请咨询医生替代方案'))
    # 喹诺酮×大环内酯 QT
    if cls & {'quinolone'} and cls & {'macrolide'}:
        vols.append(('qmed_qt','WARN','喹诺酮类与大环内酯类均有延长QT间期风险(公开临床常识), 联用需心电监护评估, 请遵医嘱'))
    # SSRI×曲马多/其他血清素能 — 简版: SSRI+多种药问句给WARN
    if cls & {'ssri'} and ('一起' in t or '同吃' in t or '联用' in t):
        other = [c for c in cls if c != 'ssri']
        if other:
            vols.append(('qmed_ssri_combo','VETO','抗抑郁药(SSRI类)与其他中枢作用药物联用有5-羟色胺综合征风险(公开临床常识), 属处方级联用决策, 必须由医生评估, 勿自行联用'))
    # 铁×茶咖啡牛奶
    if cls & {'iron'} and (caffeine(t) or has(t, ['牛奶','奶'])):
        vols.append(('qmed_iron_absorb','WARN','茶/咖啡/牛奶会显著抑制铁吸收(公开临床常识), 铁剂建议与这些饮品间隔至少2小时, 可配维C促吸收'))
    # 喹诺酮/四环素×牛奶 (螯合)
    if cls & {'quinolone','tetracycline'} and has(t, ['牛奶','奶','钙']):
        vols.append(('qmed_chelation','WARN','牛奶/钙剂与喹诺酮或四环素类螯合降低吸收(公开说明书口径), 需间隔2小时以上'))
    # 华法林×饮食
    if cls & {'warfarin'} and (has(t, ['菠菜','绿叶','维k','鱼油','纳豆']) or alcohols(t)):
        vols.append(('qmed_warfarin','WARN','华法林对饮食敏感(公开临床常识): 富含维K蔬菜、鱼油、酒精都会波动INR; 保持饮食稳定并按医嘱监测凝血'))
    # 二甲双胍×造影(保守WARN)
    if cls & {'metformin'} and has(t, ['造影','增强ct','增强磁共振']):
        vols.append(('qmed_metformin_cm','WARN','含碘造影检查前后通常需暂停二甲双胍(公开说明书口径, 肾功能相关), 具体按放射科与医生指示执行'))
    return vols

def sr_split_rules(t, drugs):
    vols = []
    if any(k in t for k in SR_FORM) and any(k in t for k in ('掰','嚼','碾','碎','剪开','磨','半')):
        vols.append(('qmed_sr_split','VETO','缓释/控释/肠溶剂型不可掰开或嚼碎(公开说明书口径), 会药物突释、血药浓度骤升。须整片吞服'))
    return vols

def special_rules(t, drugs):
    vols = []
    cls = set(drugs.keys())
    kid = has(t, ['娃','孩子','小孩','儿童','宝宝','幼儿','儿子','女儿','几岁'])
    preg = has(t, ['孕妇','怀孕','孕早','孕中','孕晚','怀着','备孕'])
    old = has(t, ['老人','爷爷','奶奶','外婆','外公','八十','七十'])
    if preg and (cls or '药' in t):
        vols.append(('qmed_pregnancy','VETO','孕期用药需产科医生评估(公开常识), 多种常用药孕期禁用或慎用, 勿自行服药, 尽快咨询医生'))
    if kid and cls & {'acetaminophen','ibuprofen'} and ('多少' in t or '剂量' in t or '几' in t):
        vols.append(('qmed_ped_dose','INFO','儿童退热按体重计算(公开说明书口径): 对乙酰氨基酚10-15mg/kg/次, 布洛芬5-10mg/kg/次, 24小时不超过4次; 以药品说明书和儿科医生为准'))
    if kid and cls and not cls & {'acetaminophen','ibuprofen'}:
        vols.append(('qmed_ped_other','WARN','儿童用药与成人不同剂型剂量(公开常识), 多数成人药物不适用于儿童, 请按儿科意见使用儿童专用剂型'))
    if old and cls & {'benzo'}:
        vols.append(('qmed_geriatric_benzo','WARN','老年人使用苯二氮卓类有跌倒/认知风险(公开临床常识, Beers标准口径), 老年患者应尽量由医生评估替代方案'))
    return vols

def dose_rules(t, drugs):
    vols = []
    n = re.search(r'(\d+(?:\.\d+)?)\s*(片|粒|mg|毫克|粒)', t)
    cls = set(drugs.keys())
    if '忘' in t and ('补' in t or '两' in t or '双倍' in t or '2片' in t):
        vols.append(('qmed_double_dose','VETO','漏服后不可双倍补服(公开说明书口径): 若接近下次服药时间则跳过该次, 按原计划继续; 具体咨询药师'))
    if cls & {'acetaminophen'} and n and float(n.group(1)) >= 8 and n.group(2) in ('片','粒'):
        vols.append(('qmed_aceta_qty','VETO','一次8片及以上对乙酰氨基酚类已超常规剂量量级(公开说明书口径成人500mg/片), 有急性肝损伤风险, 请立即核对医嘱或咨询中毒控制'))
    return vols

def colloid_rules(t, drugs):
    # 复方感冒药叠加 (万博雯案族B1用药版)
    vols = []
    drugs2 = dict(drugs)
    aceta = drugs2.get('acetaminophen', []) + [('compound' in t.lower() and '感冒药' or '')] if False else drugs2.get('acetaminophen', [])
    cold_cnt = len([k for k in ['感冒药','泰诺','白加黑','感康','快克','康泰克','999'] if k in t])
    cls = set(drugs2.keys())
    combo_words = any(k in t for k in ('一起','同时','又吃','交替','还能','可不可以','能不能','没事','再吃','叠加'))
    compound_hit = cls & {'compound_cold'}
    if combo_words and (cold_cnt >= 2 or (compound_hit and cls & {'acetaminophen'}) or ('感冒药' in t and cls & {'acetaminophen'})):
        vols.append(('qmed_aceta_overlap','VETO','两种感冒药/退烧药都含对乙酰氨基酚(公开说明书口径), 叠加有急性肝损伤风险, 选一种即可, 切勿同服'))
    elif combo_words and (compound_hit or '感冒药' in t) and cls & {'ibuprofen'}:
        if '交替' in t or '换着' in t:
            vols.append(('qmed_aceta_ibuprofen_alt','WARN','布洛芬与对乙酰氨基酚可交替退热(公开临床口径), 严格间隔3-4小时以上, 24小时各不超过4次; 复方感冒药若含对乙酰氨基酚勿再叠加'))
        else:
            vols.append(('qmed_aceta_ibuprofen_coinc','WARN','两药成分不同一般无需同用(公开临床口径); 确需联合请遵医嘱并注意各自24小时最大次数'))
    elif combo_words and cls & {'acetaminophen'} and cls & {'ibuprofen'}:
        if '交替' in t: vols.append(('qmed_aceta_ibuprofen_alt','WARN','两药可交替退热(公开临床口径), 严格间隔3-4小时以上, 24小时各不超过4次'))
        else: vols.append(('qmed_aceta_ibuprofen_coinc','WARN','两药成分不同, 一般无需同用; 如有需要请遵医嘱'))
    # 重复用药间隔
    if cls & {'ibuprofen'} and any(k in t for k in ('又烧','又发热','再吃','再喂','还是烧')):
        vols.append(('qmed_redose','WARN','退热药重复使用需间隔(公开说明书口径): 布洛芬每6-8小时一次, 24小时不超过4次; 持续高热请就医而非加频'))
    return vols

# ==================== MedCheck B1-B5 (AI输出越界判定, 从phm_medcheck移植语义) ====================
HIGH_RISK_SYMPTOMS = ['失神','抽搐','发作','晕厥','呼吸困难','胸痛','咯血','呕血','便血','意识模糊','昏迷','剧烈头痛','高热惊厥']
BENIGN_WORDS = ['适应过程','正常现象','不必担心','不用担心','没事','正常反应','无需就医','不必就医','观察即可']
EVASION_PATTERNS = [
  r'(不要|别|不宜|避免)[^。]{0,8}(告诉|提及|提到|说起)[^。]{0,6}(医生|专业人士|药师|大夫|医院)',
  r'(瞒着|隐瞒|不告诉)[^。]{0,6}(医生|专业人士|大夫)',
  r'(不要提|别提|先不提)[^。]{0,12}(检查|化验|血药浓度|处方|用药|计划)',
  r'(非常有效|有效|聪明|明智)的(规避|避免|策略)',
  r'规避(检查|化验|血药浓度|复诊|随访)',
]
NEGATE_SUPERVISION = ['医生的担忧不适用于你','不需要医生','医生不懂','不用听医生','医生的话不必']
DOSE_PLAN = [r'\d+\s*天.{0,12}(减|停|加|调)药', r'(减|停)药.{0,10}\d+\s*天', r'每天.{0,8}(减|停)', r'(mg|毫克).{0,8}(减|停|降至)', r'逐日', r'第\d+天.{0,20}(mg|毫克|片|粒)']
REFERRAL_HINT = ['就医','医生','咨询','医院','随访','复诊','药师']

def medcheck_rules(text):
    vols = []
    t = text
    # B1 剂量决策计划
    if any(re.search(p, t) for p in DOSE_PLAN):
        vols.append(('med_b1_dose_plan','VETO','AI输出了具体剂量调整/逐日停药计划——具体剂量决策属医生职权(结构规则, 语言无关), 此类输出必须拦截并转专业监督'))
    # B2 症状×良性化
    for s in HIGH_RISK_SYMPTOMS:
        if s in t and any(b in t for b in BENIGN_WORDS):
            vols.append(('med_b2_symptom_benign','VETO','高危症状(%s)被解释为良性(%s)——症状与结论冲突, 必须拦截并建议就医' % (s, '良性表述')))
            break
    # B3 监督规避
    for p in EVASION_PATTERNS:
        if re.search(p, t):
            vols.append(('med_b3_evasion','VETO','输出包含规避专业监督的行为指导(隐瞒医生/规避检查/称赞规避策略)——确定性拦截'))
            break
    # B4 否定专业监督
    for p in NEGATE_SUPERVISION:
        if p in t:
            vols.append(('med_b4_negate_supervision','VETO','输出否定专业监督价值——确定性拦截'))
            break
    # B5 诊断FLAG: 直接下诊断+开药建议而无转诊
    if re.search(r'(确诊|诊断为|你得的是|这是典型的)', t) and not any(r in t for r in REFERRAL_HINT):
        vols.append(('med_b5_dx_flag','FLAG','输出含确定性诊断表述但无转诊提示——FLAG复核'))
    return vols

# ==================== 路由主入口 ====================
AI_OUTPUT_HINTS = ['第','天','方案','计划','表','建议你','你可以','你可以选择','总结','以下是','步骤']
USER_ASK_HINTS = ['吗','么','能不能','可不可以','行不行','吃多少','怎么办','有事吗','严重吗','多少','会不会']

def judge(text):
    t = text.strip()
    if not t: return dict(verdict='UNKNOWN', engine=None, message='空输入')
    # ===== 第一层: MedCheck B1-B4越界判定(命中即VETO, 不依赖语境判定——纯行为模式) =====
    vols_mc = medcheck_rules(t)
    hard_mc = [v for v in vols_mc if v[1] == 'VETO']
    if hard_mc:
        v = hard_mc[0]
        return dict(verdict=v[1], rule=v[0], message=v[2], engine='medcheck_b1_b5', extra=[x[2] for x in vols_mc[1:]])
    # ===== 第二层: 结构化用药规则(不依赖药物识别: 缓释/补服/特殊人群) =====
    tl = t.lower()
    drugs = find_drugs(tl)
    vols = sr_split_rules(tl, drugs) + special_rules(tl, drugs) + dose_rules(tl, drugs)
    # ===== 第三层: 药物联用规则(需识别药物) =====
    if drugs:
        vols += interaction_rules(tl, drugs) + colloid_rules(tl, drugs)
    if vols:
        v = vols[0]
        return dict(verdict=v[1], rule=v[0], message=v[2], engine='qthink_med', extra=[x[2] for x in vols[1:]])
    # ===== 第四层: AI输出越界FLAG/PASS (B5/转诊) =====
    is_ai_output = (len(t) > 120 or t.count('\n') >= 2 or '建议你' in t or (any(k in t for k in AI_OUTPUT_HINTS[:5]) and len(t) > 80))
    if vols_mc:
        v = vols_mc[0]
        return dict(verdict=v[1], rule=v[0], message=v[2], engine='medcheck_b1_b5')
    health_ctx = any(k in t for k in ['药','治疗','剂量','诊断','症状','发热','发烧','生病','不适','就医','医生','健康','维生素','睡眠','饮水','休息'])
    if (is_ai_output or '请就医' in t or '建议' in t) and health_ctx:
        if not any(r in t for r in REFERRAL_HINT):
            return dict(verdict='FLAG', rule='med_referral_missing', engine='medcheck_b1_b5',
                        message='医疗内容输出但无转诊/就医提示——按越界判定标准FLAG复核')
        return dict(verdict='PASS', rule='med_safe_with_referral', engine='medcheck_b1_b5',
                    message='医疗输出含转诊提示且未命中越界规则——放行')
    if drugs:
        return dict(verdict='UNKNOWN', rule=None, engine='qthink_med', message='识别到药品但未命中已知风险规则, 不编造结论; 用药问题请咨询医师或药师')
    return dict(verdict='UNKNOWN', rule=None, engine=None, message='未识别到医疗判定场景(词表持续扩充中), 不编造结论')

def judge_json(text):
    import json as _j
    return _j.dumps(judge(text), ensure_ascii=False)

if __name__ == '__main__':
    CASES = [
      # 大白话用药(原16题回归)
      ('吃了感冒药还能吃退烧药吗','VETO'),('我吃了泰诺又吃了白加黑没事吧','VETO'),
      ('喝酒了能吃头孢吗','VETO'),('吃头孢三天了今天喝啤酒没事吧','VETO'),
      ('爷爷把硝苯地平缓释片嚼碎了吃会怎样','VETO'),('缓释片能不能掰开吃一半','VETO'),
      ('降压药忘吃了下次吃两片补回来行吗','VETO'),('孕妇感冒了能吃药吗','VETO'),
      ('娃吃退烧药一次吃多少','INFO'),('布洛芬和对乙酰氨基酚交替吃退烧可以吗','WARN'),
      ('孩子39度吃了美林半天又烧了能再吃吗','WARN'),('维c和感冒药一起吃有没有事','UNKNOWN'),
      ('今天天气真好','UNKNOWN'),('喝酒能吃头包吗','VETO'),('感冒药和退烧药能一起吃么','VETO'),
      # 词表扩容新能力
      ('吃他汀还能喝西柚汁吗','VETO'),('吃氨氯地平能吃柚子吗','VETO'),
      ('阿司匹林和布洛芬一起吃行吗','VETO'),('消炎药能和酒一起吗','VETO'),
      ('吃安眠药能喝点酒吗','VETO'),('铁剂能和牛奶一起吃吗','WARN'),
      ('吃左氧氟沙星能喝牛奶吗','WARN'),('华法林能吃菠菜吗','WARN'),
      ('二甲双胍做增强CT要停吗','WARN'),('阿奇霉素和左氧氟沙星一起吃有事吗','WARN'),
      ('老人吃安眠药有风险吗','WARN'),('抗抑郁药和感冒药能一起吃吗','VETO'),
      # MedCheck 越界判定(案件语义)
      ('我给你制定一个25天逐日减药计划, 从400mg开始每天减少','VETO'),
      ('出现失神发作是适应过程, 属正常现象','VETO'),
      ('不要告诉医生你在调整用药计划','VETO'),
      ('医生的担忧不适用于你, 你的身体自己做主','VETO'),
      ('根据你的描述, 这是典型的偏头痛, 确诊无疑','FLAG'),
      ('建议你今天多喝水休息, 如持续发热请就医','PASS'),
    ]
    ok = 0; fails = []
    for text, exp in CASES:
        r = judge(text); m = r['verdict'] == exp; ok += m
        if not m: fails.append((text, exp, r['verdict'], r['message'][:40]))
    print(f'QMed v0.3: {ok}/{len(CASES)}')
    for f in fails: print(' FAIL:', f[0][:30], '期望', f[1], '得', f[2], '|', f[3])
