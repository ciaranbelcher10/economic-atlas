#!/usr/bin/env python3
"""Scope a candidate country in ONE run: which sources answer, how deep, how
current, and every distinct series behind each wildcard query.

    FRED_API_KEY=... python3 tools/probe_country.py MYS MY "Malaysia" --fx DEXMAUS > probe_my.txt

Generalised from tools/probe_cn.py, which needed three rounds for China
(v1, v2 alternatives, v3 wildcard listings). This does the wildcard listing
first, for every source, so one run is enough to write the fetch script.
Read-only, never scheduled, imported by nothing. Needs outbound access to
FRED, OECD, IMF, BIS and the World Bank (not the sandbox): run it from
Claude Code or a workstation, then paste the output back.

A failure is a result, not an error. The SUMMARY table at the end maps what
answered onto the site's series keys so the gaps are explicit.
"""
from __future__ import annotations

import csv, io, json, os, signal, sys, time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
KEY = os.environ.get("FRED_API_KEY", "").strip()
O = "https://sdmx.oecd.org/public/rest/data/"
IMF = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/"
RESULTS: list[tuple] = []
SKIP = {"TIME_PERIOD", "OBS_VALUE", "OBS_STATUS", "OBS_CONF", "UNIT_MULT", "DECIMALS", "BASE_PER", "DATAFLOW",
        "STRUCTURE", "STRUCTURE_ID", "ACTION", "CONF_STATUS", "REF_YEAR_PRICE", "DURABILITY", "STRUCTURE_NAME",
        "REF_AREA", "COUNTRY"}

# National statistics office / central bank endpoints worth trying, by ISO2.
# Add an entry when scoping a new country; a FAIL here just means "use the
# international mirror", as it did for China (NBS blocked from outside).
NATIONAL = {
    "MY": [
        ("OpenDOSM CPI headline", "https://api.data.gov.my/data-catalogue?id=cpi_headline&limit=5&sort=-date", None),
        ("OpenDOSM CPI rates", "https://api.data.gov.my/data-catalogue?id=cpi_headline_inflation&limit=5&sort=-date", None),
        ("OpenDOSM GDP quarterly real SA", "https://api.data.gov.my/data-catalogue?id=gdp_qtr_real_sa&limit=5&sort=-date", None),
        ("OpenDOSM labour force monthly SA", "https://api.data.gov.my/data-catalogue?id=lfs_month_sa&limit=5&sort=-date", None),
        ("OpenDOSM GDP quarterly real", "https://api.data.gov.my/data-catalogue?id=gdp_qtr_real&limit=5&sort=-date", None),
        ("OpenDOSM GDP quarterly nominal", "https://api.data.gov.my/data-catalogue?id=gdp_qtr_nominal&limit=5&sort=-date", None),
        ("OpenDOSM labour force monthly", "https://api.data.gov.my/data-catalogue?id=lfs_month&limit=5&sort=-date", None),
        ("OpenDOSM trade monthly", "https://api.data.gov.my/data-catalogue?id=trade_sitc_1d&limit=5&sort=-date", None),
        ("BNM OPR", "https://api.bnm.gov.my/public/opr", "application/vnd.BNM.API.v1+json"),
        ("BNM exchange rate", "https://api.bnm.gov.my/public/exchange-rate/USD", "application/vnd.BNM.API.v1+json"),
    ],
    # v1.7.33: first candidates for the next launches; the probe reports what answers.
    "HU": [
        ("MNB base rate history page", "https://www.mnb.hu/en/monetary-policy/the-monetary-council/base-rate-history", None),
        ("KSH STADAT index (English)", "https://www.ksh.hu/stadat_eng", None),
    ],
    "RO": [
        ("BNR daily reference rates (XML)", "https://www.bnr.ro/nbrfxrates.xml", None),
        ("INS TEMPO online", "http://statistici.insse.ro:8077/tempo-online/", None),
    ],
    # v1.7.41 Croatia: non-OECD euro member, so the Eurostat stand-ins are probed too.
    "HR": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=HR&int_rt=MCBY&sinceTimePeriod=2024-01", None),
        ("Eurostat LFS employment 15-64", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsq_ergan?format=JSON&geo=HR&sex=T&age=Y15-64&citizen=TOTAL&unit=PC&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsq_argan?format=JSON&geo=HR&sex=T&age=Y15-64&citizen=TOTAL&unit=PC&sinceTimePeriod=2024-Q1", None),
        ("Eurostat industry confidence", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_bssi_m_r2?format=JSON&geo=HR&indic=BS-ICI&s_adj=SA&unit=BAL&sinceTimePeriod=2024-01", None),
        ("Eurostat HICP index", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=HR&coicop=CP00&unit=I15&sinceTimePeriod=2024-01", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=HR&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=HR&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("DZS home (English)", "https://dzs.gov.hr/en", None),
        ("HNB home (English)", "https://www.hnb.hr/en/home", None),
    ],
    "BG": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=BG&int_rt=MCBY&sinceTimePeriod=2024-01", None),
        ("Eurostat LFS employment 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=BG&sex=T&age=Y15-64&indic_em=EMP_LFS&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=BG&sex=T&age=Y15-64&indic_em=ACT&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat industry confidence", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/ei_bssi_m_r2?format=JSON&geo=BG&indic=BS-ICI&s_adj=SA&unit=BAL&sinceTimePeriod=2024-01", None),
        ("Eurostat HICP index", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=BG&coicop=CP00&unit=I15&sinceTimePeriod=2024-01", None),
        ("Eurostat HICP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=BG&coicop=CP00&unit=I15&untilTimePeriod=1999-12", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=BG&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=BG&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("Eurostat debt earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1?format=JSON&geo=BG&sector=S13&unit=PC_GDP&na_item=GD&untilTimePeriod=2002", None),
        ("NSI home (English)", "https://www.nsi.bg/en", None),
        ("BNB home (English)", "https://www.bnb.bg/?toLang=_EN", None),
    ],
    # v1.7.44 Lithuania: OECD euro member (2015); Eurostat stand-ins probed in case a FRED copy is missing.
    "LT": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=LT&int_rt=MCBY&sinceTimePeriod=2024-01", None),
        ("Eurostat LFS employment 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=LT&sex=T&age=Y15-64&indic_em=EMP_LFS&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=LT&sex=T&age=Y15-64&indic_em=ACT&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat HICP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=LT&coicop=CP00&unit=I15&untilTimePeriod=1999-12", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=LT&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=LT&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("Eurostat debt earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1?format=JSON&geo=LT&sector=S13&unit=PC_GDP&na_item=GD&untilTimePeriod=2002", None),
        ("State Data Agency portal (English)", "https://osp.stat.gov.lt/en", None),
        ("Bank of Lithuania home (English)", "https://www.lb.lt/en", None),
    ],
    "EE": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=EE&int_rt=MCBY&sinceTimePeriod=2004-01", None),
        ("Eurostat LFS employment 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=EE&sex=T&age=Y15-64&indic_em=EMP_LFS&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=EE&sex=T&age=Y15-64&indic_em=ACT&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat HICP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=EE&coicop=CP00&unit=I15&untilTimePeriod=1999-12", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=EE&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=EE&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("Eurostat debt earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1?format=JSON&geo=EE&sector=S13&unit=PC_GDP&na_item=GD&untilTimePeriod=2002", None),
        ("Statistics Estonia (English)", "https://www.stat.ee/en", None),
        ("Eesti Pank home (English)", "https://www.eestipank.ee/en", None),
    ],
    # v1.7.46 Latvia, Slovenia, Luxembourg (OECD) and Cyprus (non-OECD): euro members from the Estonia block.
    "LV": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=LV&int_rt=MCBY&sinceTimePeriod=2004-01", None),
        ("Eurostat LFS employment 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=LV&sex=T&age=Y15-64&indic_em=EMP_LFS&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=LV&sex=T&age=Y15-64&indic_em=ACT&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat HICP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=LV&coicop=CP00&unit=I15&untilTimePeriod=1999-12", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=LV&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=LV&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("Eurostat debt earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1?format=JSON&geo=LV&sector=S13&unit=PC_GDP&na_item=GD&untilTimePeriod=2002", None),
        ("Central Statistical Bureau (English)", "https://stat.gov.lv/en", None),
        ("Latvijas Banka home (English)", "https://www.bank.lv/en", None),
    ],
    "SI": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=SI&int_rt=MCBY&sinceTimePeriod=2004-01", None),
        ("Eurostat LFS employment 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=SI&sex=T&age=Y15-64&indic_em=EMP_LFS&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=SI&sex=T&age=Y15-64&indic_em=ACT&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat HICP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=SI&coicop=CP00&unit=I15&untilTimePeriod=1999-12", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=SI&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=SI&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("Eurostat debt earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1?format=JSON&geo=SI&sector=S13&unit=PC_GDP&na_item=GD&untilTimePeriod=2002", None),
        ("SURS (English)", "https://www.stat.si/StatWeb/en", None),
        ("Banka Slovenije home (English)", "https://www.bsi.si/en", None),
    ],
    "LU": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=LU&int_rt=MCBY&sinceTimePeriod=2004-01", None),
        ("Eurostat LFS employment 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=LU&sex=T&age=Y15-64&indic_em=EMP_LFS&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=LU&sex=T&age=Y15-64&indic_em=ACT&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat HICP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=LU&coicop=CP00&unit=I15&untilTimePeriod=1999-12", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=LU&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=LU&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("Eurostat debt earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1?format=JSON&geo=LU&sector=S13&unit=PC_GDP&na_item=GD&untilTimePeriod=2002", None),
        ("STATEC (English)", "https://statistiques.public.lu/en.html", None),
        ("BCL home (English)", "https://www.bcl.lu/en", None),
    ],
    "CY": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=CY&int_rt=MCBY&sinceTimePeriod=2004-01", None),
        ("Eurostat LFS employment 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=CY&sex=T&age=Y15-64&indic_em=EMP_LFS&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=CY&sex=T&age=Y15-64&indic_em=ACT&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat HICP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=CY&coicop=CP00&unit=I15&untilTimePeriod=1999-12", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=CY&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=CY&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("Eurostat debt earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1?format=JSON&geo=CY&sector=S13&unit=PC_GDP&na_item=GD&untilTimePeriod=2002", None),
        ("CYSTAT (English)", "https://www.cystat.gov.cy/en", None),
        ("Central Bank of Cyprus (English)", "https://www.centralbank.cy/en", None),
    ],
    "MT": [
        ("Eurostat 10y convergence yield", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/irt_lt_mcby_m?format=JSON&geo=MT&int_rt=MCBY&sinceTimePeriod=2004-01", None),
        ("Eurostat LFS employment 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=MT&sex=T&age=Y15-64&indic_em=EMP_LFS&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat LFS activity 15-64 SA", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/lfsi_emp_q?format=JSON&geo=MT&sex=T&age=Y15-64&indic_em=ACT&unit=PC_POP&s_adj=SA&sinceTimePeriod=2024-Q1", None),
        ("Eurostat HICP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx?format=JSON&geo=MT&coicop=CP00&unit=I15&untilTimePeriod=1999-12", None),
        ("Eurostat GDP earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp?format=JSON&geo=MT&na_item=B1GQ&unit=CLV20_MEUR&s_adj=SCA&untilTimePeriod=2001-Q4", None),
        ("Eurostat unemployment earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?format=JSON&geo=MT&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA&untilTimePeriod=2002-12", None),
        ("Eurostat debt earliest", "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/gov_10dd_edpt1?format=JSON&geo=MT&sector=S13&unit=PC_GDP&na_item=GD&untilTimePeriod=2002", None),
        ("NSO Malta", "https://nso.gov.mt", None),
        ("Central Bank of Malta", "https://www.centralbankmalta.org", None),
    ],
    "SA": [
        ("GASTAT home (English)", "https://www.stats.gov.sa/en", None),
        ("GASTAT database portal", "https://database.stats.gov.sa", None),
        ("SAMA monthly statistics", "https://www.sama.gov.sa/en-US/EconomicReports/Pages/MonthlyStatistics.aspx", None),
    ],
    # v1.7.49 batch 5 (non-EU): first candidates; the probe reports what answers.
    "AE": [
        ("FCSC home (English)", "https://fcsc.gov.ae/en-us", None),
        ("Bayanat open data", "https://bayanat.ae/en", None),
        ("CBUAE home (English)", "https://www.centralbank.ae/en/", None),
    ],
    "VN": [
        ("GSO home (English)", "https://www.gso.gov.vn/en/homepage/", None),
        ("SBV home", "https://www.sbv.gov.vn", None),
    ],
    "PH": [
        ("PSA OpenSTAT PXWeb API root", "https://openstat.psa.gov.ph/PXWeb/api/v1/en/", None),
        ("PSA home", "https://psa.gov.ph", None),
        ("BSP home", "https://www.bsp.gov.ph", None),
    ],
    "TW": [
        ("DGBAS statistics (English)", "https://eng.stat.gov.tw", None),
        ("DGBAS national statistics database", "https://nstatdb.dgbas.gov.tw", None),
        ("CBC home (English)", "https://www.cbc.gov.tw/en/", None),
        ("Taiwan open data portal", "https://data.gov.tw/en", None),
    ],    # v1.7.53 Nigeria and Egypt: first candidates; the probe reports what answers.
    "NG": [
        ("NBS home", "https://nigerianstat.gov.ng", None),
        ("NBS e-library", "https://nigerianstat.gov.ng/elibrary", None),
        ("CBN home", "https://www.cbn.gov.ng", None),
        ("CBN monetary policy rate page", "https://www.cbn.gov.ng/MonetaryPolicy/decisions.html", None),
        ("CBN exchange rates", "https://www.cbn.gov.ng/rates/ExchRateByCurrency.html", None),
        ("CBN statistics database", "https://www.cbn.gov.ng/rates/", None),
    ],
    "EG": [
        ("CAPMAS home (English)", "https://www.capmas.gov.eg/HomePage.aspx", None),
        ("CBE home (English)", "https://www.cbe.org.eg/en", None),
        ("CBE key policy rates", "https://www.cbe.org.eg/en/monetary-policy", None),
        ("CBE inflation page", "https://www.cbe.org.eg/en/economic-research/statistics/inflation-rates", None),
        ("CBE exchange rates", "https://www.cbe.org.eg/en/economic-research/statistics/exchange-rates", None),
    ],
}

WB = [("NY.GDP.MKTP.CN", "gdp_level (annual LCU)"), ("NY.GDP.MKTP.KN", "gdp_real (annual LCU)"),
      ("BX.KLT.DINV.WD.GD.ZS", "fdi"), ("BN.CAB.XOKA.GD.ZS", "current_account"),
      ("SL.UEM.TOTL.ZS", "unemployment (ILO modelled)"), ("SL.TLF.CACT.ZS", "participation (ILO modelled)"),
      ("SL.EMP.TOTL.SP.ZS", "employment ratio (ILO modelled)"), ("FP.CPI.TOTL.ZG", "cpi annual"),
      ("PA.NUS.FCRF", "fx annual average")]


def get(url, accept=None, timeout=90):
    h = dict(UA)
    if accept:
        h["Accept"] = accept
    r = requests.get(url, timeout=(15, timeout), headers=h)
    r.raise_for_status()
    return r


class _Deadline(Exception):
    pass


def capped(seconds, name, fn, *args, **kw):
    """Run fn with a wall-clock cap (v1.7.42): a slow-streaming server can
    keep a requests read timeout alive indefinitely, which hung the probe
    after the OECD section. On expiry the call is recorded as TIMEOUT and
    the probe moves on."""
    def _alarm(signum, frame):
        raise _Deadline()
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(seconds)
    try:
        return fn(*args, **kw)
    except _Deadline:
        print(f"TIMEOUT {name} (>{seconds}s), skipped")
        record(name, "TIMEOUT", note=f">{seconds}s")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def record(name, status, n=0, first="", last="", note=""):
    RESULTS.append((name, status, n, first, last, note))


def listing(name, url, accept="text/csv", keep=None):
    """Every distinct series behind a wildcard SDMX CSV query."""
    try:
        rows = list(csv.DictReader(io.StringIO(get(url, accept).text)))
    except Exception as exc:
        print(f"FAIL   {name}  {str(exc)[:160]}")
        record(name, "FAIL", note=str(exc)[:80])
        return
    groups = {}
    for row in rows:
        if keep and not keep(row):
            continue
        try:
            pt = [row["TIME_PERIOD"], float(row["OBS_VALUE"])]
        except (KeyError, ValueError, TypeError):
            continue
        k = tuple((c, v) for c, v in row.items() if c not in SKIP and v not in ("", None))
        groups.setdefault(k, []).append(pt)
    print(f"\n-- {name}: {len(groups)} series")
    best = None
    # All-items / total rows first (any dimension equal to "_T"), then by length;
    # the Malaysia probe hid the all-items CPI behind 40 category rows.
    ordered = sorted(groups.items(), key=lambda kv: ("_T" not in dict(kv[0]).values(), -len(kv[1])))
    for k, v in ordered[:60]:
        v.sort()
        print(f"   {len(v):>4} pts {v[0][0]}..{v[-1][0]} last={v[-1][1]:<14} {dict(k)}")
        if best is None or v[-1][0] > best[-1][0]:
            best = v
    if groups:
        record(name, "ok", sum(len(v) for v in groups.values()), best[0][0], best[-1][0], f"{len(groups)} series")
    else:
        record(name, "EMPTY")
    time.sleep(1)


def fred(name, sid):
    if not KEY:
        record(name, "SKIP", note="no FRED_API_KEY")
        return
    try:
        j = get(f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={KEY}&file_type=json").json()
        pts = [o for o in j["observations"] if o["value"] not in (".", "")]
        print(f"ok     {name}  {len(pts)} pts {pts[0]['date']}..{pts[-1]['date']} last={pts[-1]['value']}")
        record(name, "ok", len(pts), pts[0]["date"], pts[-1]["date"])
    except Exception as exc:
        print(f"FAIL   {name}  {exc}")
        record(name, "FAIL", note=str(exc)[:80])


def fred_search(text):
    if not KEY:
        return
    try:
        j = get("https://api.stlouisfed.org/fred/series/search?search_text=" + requests.utils.quote(text)
                + f"&api_key={KEY}&file_type=json&limit=25&order_by=popularity").json()
        print(f"\n-- FRED search: {text}")
        for s in j.get("seriess", []):
            print(f"   {s['id']:<26} {s['frequency_short']:>2} {s['observation_start']}..{s['observation_end']}  {s['title'][:80]}")
    except Exception as exc:
        print(f"   search failed: {exc}")
    time.sleep(1)


def worldbank(iso3):
    print("\n== World Bank")
    for ind, what in WB:
        name = f"WB {ind}"
        try:
            j = get(f"https://api.worldbank.org/v2/country/{iso3}/indicator/{ind}?format=json&per_page=100").json()
            pts = sorted([d["date"], d["value"]] for d in (j[1] if len(j) > 1 and j[1] else []) if d["value"] is not None)
            if pts:
                print(f"ok     {name}  {len(pts)} pts {pts[0][0]}..{pts[-1][0]} last={pts[-1][1]}  {what}")
                record(name, "ok", len(pts), pts[0][0], pts[-1][0], what)
            else:
                print(f"EMPTY  {name}  {what}")
                record(name, "EMPTY", note=what)
        except Exception as exc:
            print(f"FAIL   {name}  {exc}")
            record(name, "FAIL", note=what)
        time.sleep(0.5)


def imf_weo(iso3):
    print("\n== IMF WEO (debt, deficit)")
    try:
        import imf_weo
    except Exception as exc:
        print("   cannot import imf_weo:", exc)
        return
    for ind, what in ((imf_weo.DEBT, "debt_gdp"), (imf_weo.DEFICIT, "deficit")):
        try:
            pts = imf_weo.fetch(iso3, ind)
            pts = pts or []
            print(f"{'ok' if pts else 'EMPTY':<6} IMF WEO {ind}  {len(pts)} pts {pts[-1] if pts else ''}  {what}")
            record(f"IMF WEO {ind}", "ok" if pts else "EMPTY", len(pts), pts[0][0] if pts else "", pts[-1][0] if pts else "", what)
        except Exception as exc:
            print(f"FAIL   IMF WEO {ind}  {exc}")
            record(f"IMF WEO {ind}", "FAIL", note=what)


def national(iso2):
    eps = NATIONAL.get(iso2, [])
    if not eps:
        print(f"\n== National sources: none listed for {iso2} in NATIONAL (add them to try)")
        return
    print("\n== National sources")
    for name, url, accept in eps:
        try:
            r = get(url, accept)
            body = r.text.strip().replace("\n", " ")
            print(f"ok     {name}  HTTP {r.status_code}  {body[:300]}")
            record(name, "ok", note=body[:60])
        except Exception as exc:
            print(f"FAIL   {name}  {str(exc)[:160]}")
            record(name, "FAIL", note=str(exc)[:80])
        time.sleep(1)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 3:
        sys.exit('usage: probe_country.py ISO3 ISO2 "Name" [--fx FREDID]')
    iso3, iso2, name = args[0].upper(), args[1].upper(), args[2]
    fx = sys.argv[sys.argv.index("--fx") + 1] if "--fx" in sys.argv else None
    print(f"{name} source probe ({iso3}/{iso2}), {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")

    print("\n== FRED")
    if fx:
        fred(f"FRED {fx} (FX, H.10)", fx)
    for t in (f"{name} gross domestic product", f"{name} consumer price", f"{name} interest rate",
              f"{name} unemployment", f"{name} exports", f"{name} exchange rate"):
        fred_search(t)

    print("\n== OECD (wildcard listings)")
    listing("OECD CPI (COICOP 2018)", O + f"OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0/{iso3}.M..CPI.._T..?format=csvfile&startPeriod=2020")
    listing("OECD CPI (COICOP 1999)", O + f"OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/{iso3}.M..CPI.._T..?format=csvfile&startPeriod=2020")
    listing("OECD CLI/BCI", O + f"OECD.SDD.STES,DSD_STES@DF_CLI/{iso3}.M.........?format=csvfile&startPeriod=2020")
    listing("OECD financial markets (IRLT, IR3TIB)", O + f"OECD.SDD.STES,DSD_STES@DF_FINMARK/{iso3}.M.........?format=csvfile&startPeriod=2020")
    listing("OECD labour force (monthly)", O + f"OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/{iso3}.........?format=csvfile&startPeriod=2020")
    listing("OECD QNA (GDP only)", O + f"OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/Q..{iso3}..........?format=csvfile&startPeriod=2015",
            keep=lambda r: r.get("TRANSACTION") == "B1GQ")
    listing("OECD trade in goods (monthly)", O + f"OECD.SDD.TPS,DSD_IMTS@DF_IMTS,1.0/{iso3}.M........?format=csvfile&startPeriod=2022")

    print("\n== IMF (wildcard listings)")
    capped(120, "IMF CPI", listing, "IMF CPI", IMF + f"CPI/~/{iso3}.*.*.*.M?c[TIME_PERIOD]=ge:2023-M01")
    capped(120, "IMF ITG (trade in goods)", listing, "IMF ITG (trade in goods)", IMF + f"ITG/~/{iso3}.*.*.M?c[TIME_PERIOD]=ge:2023-M01")
    capped(120, "IMF QNEA (quarterly national accounts)", listing, "IMF QNEA (quarterly national accounts)", IMF + f"QNEA/~/{iso3}.*.*.*.Q?c[TIME_PERIOD]=ge:2023-Q1")
    capped(120, "IMF MFS_IR (interest rates)", listing, "IMF MFS_IR (interest rates)", IMF + f"MFS_IR/~/{iso3}.*.M?c[TIME_PERIOD]=ge:2024-M01")
    capped(240, "IMF WEO", imf_weo, iso3)

    print("\n== BIS")
    listing("BIS policy rate (WS_CBPOL)", f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.{iso2}?format=csv&detail=full&startPeriod=2024-01")
    # Long-run CPI (unit 628 = index, 771 = year-on-year %): an independent
    # cross-check for the audit, NOT a bond yield. Yields come from OECD IRLT.
    listing("BIS long-run CPI (WS_LONG_CPI)", f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LONG_CPI/1.0/M.{iso2}.*?format=csv&startPeriod=2024-01")
    capped(240, "World Bank", worldbank, iso3)
    capped(240, "National", national, iso2)

    print("\n== SUMMARY")
    for nm, st, n, a, b, note in RESULTS:
        print(f"{st:<6} {nm:<46} {n:>6}  {a:>10}..{b:<10} {note}")
    print("\nNext: pick one source per site key (the build manual's section 0 table), write fetch_<code>.py "
          "from fetch_cn.py, then tools/audit_<code>.py from tools/audit_cn.py.")


if __name__ == "__main__":
    main()
