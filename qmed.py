# -*- coding: utf-8 -*-
# QMed v0.3 — 统一医疗判定引擎 (QThink-Med用药判定 × MedCheck越界判定)
# 知识源: 公开OTC/说明书口径+公开临床常识, 保守取值; 三态出口; 不编造纪律
# 路由: AI输出(长文/计划/安抚语气) -> MedCheck B1-B5越界判定
#       用户提问(口语/药物+联用) -> 用药安全判定
#       都不是 -> UNKNOWN如实拒答
import re, sys, os

__version__ = "0.3.0"