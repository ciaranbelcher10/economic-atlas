// Behavioural tests for Compare's complete-year and measure rules, run on
// compare.html's own code.   node tools/test_compare_rules.js
// Synthetic series are swapped into the page's registry for the unit cases;
// the invariants at the end run over every real country, metric and year.
const {load} = require('./compare_values.js');

(async () => {
  const A = await load();
  const R = A.REGISTRY;
  const Y = A.lastEndedYear();
  const results = [];
  const check = (name, got, want) => results.push({name, ok: JSON.stringify(got) === JSON.stringify(want), got, want});
  const months = (y, skip = []) => Array.from({length: 12}, (_, i) => [`${y}-${String(i + 1).padStart(2, '0')}`, i + 1]).filter(p => !skip.includes(p[0]));
  const quarters = (y, vals, skip = []) => vals.map((v, i) => [`${y}-Q${i + 1}`, v]).filter(p => !skip.includes(p[0]));
  const withSeries = (country, series, fn) => {
    const saved = R[country]; R[country] = series;
    try { return fn(); } finally { R[country] = saved; }
  };
  const val = (country, concept, year) => { const v = A.getSnapshotValue(country, concept, year); return v ? v.value : null; };

  // averaged metrics
  withSeries('UK', {cpi: {label: 'CPI annual rate, all items (D7G7)', unit: '%', freq: 'months', points: months(Y)}}, () => {
    check('12 months average', val('UK', 'cpi', Y), 6.5);
  });
  withSeries('UK', {cpi: {label: 'x (D7G7)', unit: '%', freq: 'months', points: months(Y, [`${Y}-10`])}}, () => {
    check('interior gap still averages the readings present', val('UK', 'cpi', Y), Math.round((78 - 10) / 11 * 100) / 100);
    check('interior gap is disclosed', /Oct .* no reading/.test(A.yearCoverageNote('UK', 'cpi', Y)), true);
  });
  withSeries('UK', {cpi: {label: 'x', unit: '%', freq: 'months', points: months(Y, [`${Y}-12`])}}, () => {
    check('missing December means no figure', val('UK', 'cpi', Y), null);
  });
  withSeries('UK', {cpi: {label: 'x', unit: '%', freq: 'months', points: months(Y, [`${Y}-01`])}}, () => {
    check('missing January means no figure', val('UK', 'cpi', Y), null);
  });
  withSeries('UK', {cpi: {label: 'x', unit: '%', freq: 'months', points: months(Y + 1)}}, () => {
    check('a year that has not ended is never shown', val('UK', 'cpi', Y + 1), null);
    check('and the reason says so', A.noDataReason('UK', 'cpi', Y + 1), `${Y + 1} has not ended yet.`);
  });

  // flows are totals and need every period
  withSeries('UK', {trade_balance: {label: 't', unit: '$m', freq: 'months', points: months(Y)}}, () => {
    check('monthly flow is the year total', val('UK', 'trade_balance', Y), 78);
  });
  withSeries('UK', {trade_balance: {label: 't', unit: '$m', freq: 'months', points: months(Y, [`${Y}-06`])}}, () => {
    check('a flow with a missing month has no figure', val('UK', 'trade_balance', Y), null);
  });
  withSeries('UK', {trade_balance: {label: 't', unit: '$m', freq: 'quarters', points: quarters(Y, [10, 20, 30, 40])}}, () => {
    check('quarterly flow is the year total', val('UK', 'trade_balance', Y), 100);
  });

  // stocks are end of year
  withSeries('UK', {debt_gdp: {label: 'd', unit: '%', freq: 'quarters', points: quarters(Y, [40, 41, 42, 53])}}, () => {
    check('debt ratio is the year-end value', val('UK', 'debt_gdp', Y), 53);
  });

  // GDP
  withSeries('US', {gdp_level: {label: 'g', unit: '$m', freq: 'quarters', points: quarters(Y, [100, 110, 120, 130])}}, () => {
    check('annual-rate quarters are averaged (US)', val('US', 'gdp_level', Y), 115);
  });
  withSeries('Germany', {gdp_level: {label: 'g', unit: '$m', freq: 'quarters', points: quarters(Y, [100, 110, 120, 130])}}, () => {
    check('ordinary quarters are summed', A.yearAggregate('Germany', 'gdp_level', Y).value, 460);
  });
  withSeries('Germany', {gdp_level: {label: 'g', unit: '$m', freq: 'quarters', points: quarters(Y, [100, 110, 120, 130], [`${Y}-Q2`])}}, () => {
    check('GDP with a missing quarter has no figure', A.yearAggregate('Germany', 'gdp_level', Y), null);
  });
  withSeries('US', {gdp_real: {label: 'r', unit: '$m', freq: 'quarters', points: quarters(Y - 1, [100, 100, 100, 100]).concat(quarters(Y, [102, 102, 103, 103]))}}, () => {
    check('growth compares annual GDP', val('US', 'gdp_growth', Y), 2.5);
  });
  withSeries('Chile', {gdp_level: {label: 'g', unit: '$m', freq: 'years', points: [[String(Y), 777]]}}, () => {
    check('annual GDP is used as published', A.yearAggregate('Chile', 'gdp_level', Y).value, 777);
  });

  // units and measures
  withSeries('UK', {deficit: {label: 'PSNB', unit: '£m', freq: 'months', points: months(Y)}}, () => {
    check('a currency deficit never answers a % card', A.resolveKey('UK', 'deficit'), null);
    check('and the reason names the unit', /£m/.test(A.noDataReason('UK', 'deficit', Y)), true);
  });
  withSeries('Sweden', {
    cpi: {label: 'HICP, all items, YoY (Eurostat, CP0000SEM086NEST)', unit: '%', freq: 'months', points: months(Y)},
    cpi_national: {label: 'CPI, national definition', unit: '%', freq: 'months', points: months(Y)},
  }, () => {
    check('HICP card takes the HICP series', A.resolveKey('Sweden', 'cpi_hicp'), 'cpi');
    check('national card takes the national series', A.resolveKey('Sweden', 'cpi_national'), 'cpi_national');
    check('HICP is tagged', A.measureTag('Sweden', 'cpi'), 'HICP');
  });
  withSeries('Germany', {cpi: {label: 'HICP, all items, YoY (CP0000DEM086NEST)', unit: '%', freq: 'months', points: months(Y)}}, () => {
    check('an HICP is never shown as a national CPI', A.resolveKey('Germany', 'cpi_national'), null);
  });
  withSeries('US', {cpi: {label: 'CPI, all items, YoY, not seasonally adjusted (CPIAUCNS)', unit: '%', freq: 'months', points: months(Y)}}, () => {
    check('a national CPI is never shown as HICP', A.resolveKey('US', 'cpi_hicp'), null);
  });

  // invariants over the real data
  check('latest selectable year has ended', A.CURRENT_YEAR <= Y, true);
  check('map shows exactly the bar value', JSON.stringify(A.getMapValueForYear('US', 'gdp_level', A.CURRENT_YEAR)) === JSON.stringify(A.getSnapshotValue('US', 'gdp_level', A.CURRENT_YEAR)), true);
  check('policy rate card cites a real source', !!A.metricSourceNote('UK', 'policy_rate'), true);
  let unitBreaches = 0, unexplained = 0, beyond = 0, shown = 0;
  for(const concept of Object.keys(A.CONCEPT_UNIT)){
    for(const country of A.ALL_COUNTRIES){
      const pts = A.historyPoints(country, concept) || [];
      if(pts.some(p => +String(p[0]).slice(0, 4) > A.CURRENT_YEAR)) beyond++;
      if(concept !== 'gdp_growth'){
        const key = A.resolveKey(country, concept);
        if(key && !A.unitCompatible(concept, R[country][key])) unitBreaches++;
      }
      for(let y = 2000; y <= Y + 1; y++){
        const v = A.getSnapshotValue(country, concept, y);
        if(!v) continue;
        shown++;
        if(y > Y) beyond++;
        if(!A.yearCoverageNote(country, concept, y)) unexplained++;
      }
    }
  }
  check('no card resolves a series in the wrong unit', unitBreaches, 0);
  check('no value is shown for a year that has not ended, and no trend line runs past the latest year', beyond, 0);
  check('every value shown has a note saying how it was built', unexplained, 0);

  const bad = results.filter(r => !r.ok);
  bad.forEach(r => console.log(`FAIL ${r.name}: got ${JSON.stringify(r.got)}, want ${JSON.stringify(r.want)}`));
  console.log(`${results.length - bad.length}/${results.length} compare rule branches pass (${shown} real values checked for the invariants)`);
  process.exit(bad.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
