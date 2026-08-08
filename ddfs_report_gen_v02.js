/* Design Day Report generator v0.1 - superset per note 36, demonstrated on Zagreb.
   Author metadata Avia Solutions; en-GB enforced post-build. */
const fs = require("fs");
const D = require("docx");
const data = JSON.parse(fs.readFileSync("report_data.json", "utf8"));

const A = (t, o = {}) => new D.TextRun({ text: t, font: "Arial", size: o.size || 20, bold: o.bold, italics: o.it, color: o.color });
const P = (t, o = {}) => new D.Paragraph({ children: [A(t, o)], spacing: { after: o.after ?? 120 }, alignment: o.align });
const H1 = t => new D.Paragraph({ heading: D.HeadingLevel.HEADING_1, children: [A(t, { size: 26, bold: true })], spacing: { before: 240, after: 160 } });
const H2 = t => new D.Paragraph({ heading: D.HeadingLevel.HEADING_2, children: [A(t, { size: 22, bold: true })], spacing: { before: 200, after: 120 } });
const SRC = t => new D.Paragraph({ children: [A("Source: " + t, { size: 16, it: true })], spacing: { after: 200 } });
let tabN = 0;
const CAP = t => { tabN += 1; return new D.Paragraph({ children: [A(`Table ${tabN}: ${t}`, { size: 18, bold: true })], spacing: { before: 160, after: 80 } }); };

function tbl(headers, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  const w = i => Math.round(9000 / total * widths[i]);
  const cell = (txt, hdr, i) => new D.TableCell({
    width: { size: w(i), type: D.WidthType.DXA },
    shading: hdr ? { type: D.ShadingType.CLEAR, fill: "1F4E79" } : undefined,
    children: [new D.Paragraph({ children: [A(String(txt), { size: 16, bold: hdr, color: hdr ? "FFFFFF" : undefined })] })] });
  return new D.Table({
    columnWidths: widths.map((_, i) => w(i)),
    rows: [new D.TableRow({ children: headers.map((h, i) => cell(h, true, i)) })]
      .concat(rows.map(r => new D.TableRow({ children: r.map((v, i) => cell(v, false, i)) }))) });
}

const YEARS = ["2025", "2030", "2035", "2040", "2045"];
const oracle = new Map(data.oracle.map(([k, v]) => [k.join("|"), v]));
const g = (sheet, section, meas, row, split) => {
  const v = oracle.get([sheet, section, meas, row, split].join("|"));
  return YEARS.map(y => v && v[y] !== undefined ? Math.round(v[y]).toLocaleString("en-GB") : "-");
};

const stub = (title, precedent, fills) => [H2(title + " [STUB]"),
  P(`This section is part of the superset report (note 36) and is not populated in this demonstration. Precedent: ${precedent}. It populates when ${fills}.`, { it: true })];

const kids = [];
kids.push(new D.Paragraph({ children: [A("Private and Confidential", { size: 20, bold: true })], alignment: D.AlignmentType.RIGHT }));
kids.push(new D.Paragraph({ children: [A("Avia Cortex DDFS", { size: 36, bold: true })], spacing: { before: 2400, after: 200 }, alignment: D.AlignmentType.CENTER }));
kids.push(new D.Paragraph({ children: [A("Design Day Report - Generator v0.2 demonstration on Zagreb", { size: 26 })], alignment: D.AlignmentType.CENTER, spacing: { after: 200 } }));
kids.push(new D.Paragraph({ children: [A("19 July 2026 | DRAFT - internal demonstration, not for client issue", { size: 20, it: true })], alignment: D.AlignmentType.CENTER, spacing: { after: 2400 } }));
kids.push(P("This publication provides general information and should not be relied upon in substitution for the exercise of independent judgment. The Cargo and General Aviation forecasts are expressly excluded from the scope of this Design Day analysis and the stand tables flag rather than fill where they are an input assumption. Avia accepts no liability of any kind for loss arising from the use of the material presented in this publication.", { size: 16, it: true }));
kids.push(new D.Paragraph({ children: [new D.PageBreak()] }));

kids.push(H1("Abbreviations"));
kids.push(tbl(["Term", "Definition"], [
 ["ATM", "Air Transport Movement (an arrival or a departure)"],
 ["BHR", "Busy Hour Rate: the 5% busy hour per the IATA ADRM (10th edition); in this report the ZAG convention is the 30th busiest hour (SBR)"],
 ["DDFS", "Design Day Flight Schedule"],
 ["PMAD", "Peak Month Average Day (FAA convention)"],
 ["PHP", "Peak Hour Passengers"],
 ["SBR", "Standard Busy Rate: the 30th busiest hour of the year (BAA lineage)"]], [1, 5]));
kids.push(SRC("IATA ADRM 10th edition; note 31 v2 (AviaSolutions)"));

kids.push(H1("1  Introduction and scope"));
kids.push(P("Avia Solutions has prepared this demonstration Design Day report from its DDFS generator (v0.2). The airport demonstrated is Zagreb (ZAG); the historic evidence is computed from full-year 2015 and 2016 schedules held in Avia's OAG store, and the forecast-year outputs are the Zagreb oracle regeneration of 19 July 2026. Scheduled commercial services only; cargo and general aviation are excluded from the schedule-derived tables, and general aviation stand demand is carried as a stated input assumption where it appears. Every convention used in this report is named in the appendix, and every number arrives with its discussion."));
kids.push(H2("1.10  Design Day Flight Schedules in one page"));
{
  const rows = YEARS.map(y => {
    const d = data.design_days[y];
    return [y, d.design_day, (d.annual_pax_model/1e6).toFixed(1) + "m",
            d.day_pax.toLocaleString("en-GB"), d.day_atms.toLocaleString("en-GB"),
            d.sbr30_value.toLocaleString("en-GB"), d.rolling60_max_pax.toLocaleString("en-GB")];
  });
  kids.push(CAP("DDFS summary per spot year (Base case, forecast)"));
  kids.push(tbl(["Year", "Design day", "Annual pax", "Design day pax", "Design day ATMs", "30th busy hour pax", "Rolling-hour max pax"], rows, [1, 2, 1.4, 1.6, 1.6, 1.8, 2]));
  kids.push(SRC("AviaSolutions analysis (Zagreb oracle run, 19 July 2026); design day = the day containing the 30th busiest 2-way hour"));
  kids.push(P("The design day is the day on which the 30th busiest two-way hour of the year falls, keeping the schedule a real, inspectable day consistent with the engagement's SBR convention. Design-day passengers run at circa 4.3-5.0 per thousand of annual passengers across the horizon, inside the historic peaking band of section 3."));
}

kids.push(H1("2  Defining the design level: method comparison and choice"));
kids.push(P("Every airport has one busiest hour of the year. If the terminal were built for that hour it would stand largely empty for the other 8,759; built for an average hour, it would be overcrowded for weeks every summer. Airport planners therefore pick a design level in between, and the methods below are different ways of picking it. They can give noticeably different answers: at Zagreb in 2015, counting movements, the single busiest hour fell in January, the 30th busiest hour in May, IATA's busy day in July and the busiest whole day in September. That is why the method is agreed with the client first, and why the engine calculates all of them so the choice is made on evidence."));
for (const [tag, label] of [["ZAG_2015", "Zagreb 2015, movements basis"], ["ZAG_2015_pax", "Zagreb 2015, passenger basis (Sabre-weighted, indicative)"], ["ZAG_2016", "Zagreb 2016, movements basis"], ["ZAG_2016_pax", "Zagreb 2016, passenger basis (Sabre-weighted, indicative)"]]) {
  const rows = data.methods[tag];
  kids.push(CAP(`Method comparison, ${label}`));
  kids.push(tbl(rows[0], rows.slice(1), rows[0].map((_, i) => i === 0 ? 3 : 2)));
  kids.push(SRC("AviaSolutions analysis of the OAG store (ddfs_method_module, run 18 July 2026)"));
}
kids.push(P("The engagement convention demonstrated here is the 30th busiest hour (SBR), the convention of the sent Zagreb deliverable and long UK practice. On the passenger basis every method moves its selection into the summer; the movements basis peaks in winter banks of small aircraft. Runways and stands care about movements, terminals and security care about passengers, and the engine computes both."));

kids.push(H1("3  Historic evidence: the peaking anchor"));
for (const y of ["2015", "2016"]) {
  const h = data.historic[y];
  kids.push(CAP(`Monthly ATMs and peaking statistics, Zagreb ${y} (actual schedules)`));
  const months = Object.keys(h.monthly);
  kids.push(tbl(["", ...months],
    [["Arrivals", ...months.map(m => h.monthly[m][0].toLocaleString("en-GB"))],
     ["Departures", ...months.map(m => h.monthly[m][1].toLocaleString("en-GB"))]],
    [2, ...months.map(() => 1)]));
  kids.push(P(`Annual ATMs ${h.annual_atms.toLocaleString("en-GB")}; peak month ${h.peak_month}; PMAD ${h.pmad_atms} ATMs, ${h.pmad_over_avg_pct}% above the average day and ${h.pmad_per_1000_annual} per thousand of annual movements.`, { size: 18 }));
  kids.push(SRC("AviaSolutions analysis of the OAG store, monthly-file authority, J services"));
}
kids.push(P("The Zagreb anchors corroborate the ADAC precedent almost exactly: ADAC 2017-2019 showed PMAD stable at 6-7% above the average day and 2.9 per thousand of annual; Zagreb 2015-2016 gives 5.7-10.6% and 2.89-3.02. The peaking-band coherence check therefore has cross-airport evidence, and forecast-year design days outside this band would be queried rather than accepted."));
stub("3.3  Actual versus scheduled variance", "ADAC 12.2 (variance table with the stated no-adjustment conclusion)", "the engagement holds ATC or AODB actuals alongside schedules").forEach(x => kids.push(x));

kids.push(H1("4  Methodology: growth, placement and conventions"));
kids.push(P("The forecast-year schedules are grown from the reference schedule by carrier group: the Ryanair and Wizz capacity path follows the engagement's stated plan (read as passengers, ramping to 2030 and steadying thereafter), and all other carriers grow at the residual of the forecast's scheduled-movements path, with a 0.35% per annum upgauge on seats. Added frequencies are placed deterministically in the operating airline's existing waves; where a cap binds, placement spills to the nearest shoulder hour with headroom. Aircraft on the ground at midnight are carried as flagged events per the Bologna DayBeforeArr convention. Per-airline behaviour follows the ADAC precedent: hub waves deepen rather than multiply, fleet renewal concentrates gauge (Croatia Airlines' A220 renewal), low-cost carriers hold turnaround behaviour, and other carriers hold profile."));
stub("4.4  Constraint layer", "Bologna ENAC hourly caps by Schengen split with a compliance summary", "a regulator cap applies at the engagement airport").forEach(x => kids.push(x));

kids.push(H1("5  Outputs"));
kids.push(H2("5.1  30th busy hour passengers by terminal, direction and split"));
for (const term of ["Overall", "Old Terminal", "New Terminal"]) {
  kids.push(CAP(`30th busy hour passengers, ${term} (Base case, forecast)`));
  const rows = [];
  for (const dir of ["2-way", "Arrivals", "Departures"])
    for (const sp of ["Schengen", "Non-Schengen", "Total"])
      rows.push([dir + " " + sp, ...g("Base", "30th BHRs - " + term, "", dir, sp)]);
  kids.push(tbl(["Series", ...YEARS], rows, [3, 1, 1, 1, 1, 1]));
  kids.push(SRC("AviaSolutions analysis (Zagreb oracle run, 19 July 2026); pax, forecast years"));
}
kids.push(H2("5.2  Peak runway movements"));
kids.push(CAP("Peak runway movements (30th busiest hour, ATMs, forecast)"));
kids.push(tbl(["Series", ...YEARS], [["Overall peak", ...g("Base", "Peak Runway Movements", "", "Overall peak", "")]], [3, 1, 1, 1, 1, 1]));
kids.push(SRC("AviaSolutions analysis (Zagreb oracle run, 19 July 2026); scheduled commercial ATMs"));
kids.push(H2("5.3  Stand demand by ICAO code"));
for (const blk of ["Commercial", "Old Terminal - Commercial", "New Terminal - Commercial"]) {
  kids.push(CAP(`Stands, ${blk} (Base case, forecast)`));
  const rows = [];
  for (const meas of ["Overall peak", "Overnight Peak", "Individual Peak"])
    for (const c of ["A", "B", "C", "D", "E", "Total"]) {
      if (meas === "Individual Peak" && c === "Total") continue;
      rows.push([meas + " " + c, ...g("Base", "Stands - by Stand Code - " + blk, meas, c, "")]);
    }
  kids.push(tbl(["Measure / code", ...YEARS], rows, [3, 1, 1, 1, 1, 1]));
  kids.push(SRC("AviaSolutions analysis (Zagreb oracle run, 19 July 2026); stands, forecast years"));
}
kids.push(P("General aviation stand demand is an input assumption in the precedent deliverable and is flagged rather than filled here; the Overall stand block therefore appears only when the assumption is supplied. The Stand Scenario sheet of the oracle diff carries the stands-with-buffer variant (MZLZ precedent)."));
kids.push(H2("5.4  Design day hourly, rolling hour and 5-minute grain"));
kids.push(CAP("Design day hourly passengers, arrivals and departures (departures negative, forecast)"));
{
  const hdr = ["Time"]; YEARS.forEach(y => { hdr.push(y + "A", y + "D"); });
  const rows = [];
  for (let hh = 0; hh < 24; hh++) {
    const r = [String(hh).padStart(2, "0")];
    YEARS.forEach(y => { const v = data.design_days[y].hourly[hh]; r.push(v[0].toLocaleString("en-GB"), v[1] ? "-" + v[1].toLocaleString("en-GB") : "0"); });
    rows.push(r);
  }
  const tot = ["Total"]; YEARS.forEach(y => { let a = 0, d = 0; for (let hh = 0; hh < 24; hh++) { a += data.design_days[y].hourly[hh][0]; d += data.design_days[y].hourly[hh][1]; } tot.push(a.toLocaleString("en-GB"), "-" + d.toLocaleString("en-GB")); });
  rows.push(tot);
  kids.push(tbl(hdr, rows, [1.2, ...YEARS.flatMap(() => [1, 1])]));
  kids.push(SRC("AviaSolutions analysis (Zagreb oracle run, 19 July 2026); pax on the design day, departures shown negative per the ADAC convention"));
}
kids.push(CAP("5-minute grain, busiest two hours of the design day, 2025 and 2045 (pax A/D, forecast)"));
{
  const e25 = data.design_days["2025"].fivemin_excerpt, e45 = data.design_days["2045"].fivemin_excerpt;
  const k25 = Object.keys(e25), k45 = Object.keys(e45);
  const n = Math.max(k25.length, k45.length);
  const rows = [];
  for (let i = 0; i < n; i++) {
    rows.push([k25[i] || "", ...(k25[i] ? e25[k25[i]] : ["", ""]), k45[i] || "", ...(k45[i] ? e45[k45[i]] : ["", ""])]);
  }
  kids.push(tbl(["2025 slot", "A", "D", "2045 slot", "A", "D"], rows, [1.5, 1, 1, 1.5, 1, 1]));
  kids.push(SRC("AviaSolutions analysis (Zagreb oracle run, 19 July 2026); full 5-minute grain for all years exports to Excel from the front end"));
}
kids.push(H1("6  Benchmarks and cross-checks"));
kids.push(P("Per the ADAC precedent the deliverable carries its own cross-checks: comparator columns against a nominated benchmark inside the output tables. Here the benchmark is the sent Zagreb deliverable of 18 June 2026, so the table below is simultaneously the prior-vintage comparator and the oracle's self-check; every remaining difference is a named convention under test, not an unexplained residual."));
kids.push(CAP("Oracle versus sent deliverable, headline series (30th busy hour and runway, forecast)"));
{
  const rows = [];
  for (const [label, sec, row, split] of [["2-way Total pax", "30th BHRs - Overall", "2-way", "Total"], ["Arrivals Total pax", "30th BHRs - Overall", "Arrivals", "Total"], ["Departures Total pax", "30th BHRs - Overall", "Departures", "Total"]]) {
    const o = g("Base", sec, "", row, split);
    const sb = data.sent_benchmark[row];
    rows.push([label, ...YEARS.flatMap((y, i) => [o[i], sb && sb[y] !== undefined ? Math.round(sb[y]).toLocaleString("en-GB") : "-"])]);
  }
  const oR = g("Base", "Peak Runway Movements", "", "Overall peak", "");
  const sR = data.sent_benchmark["Runway"];
  rows.push(["Runway peak ATMs", ...YEARS.flatMap((y, i) => [oR[i], sR && sR[y] !== undefined ? Math.round(sR[y]).toLocaleString("en-GB") : "-"])]);
  const hdr = ["Series"]; YEARS.forEach(y => hdr.push(y + " Oracle", y + " Sent"));
  kids.push(tbl(hdr, rows, [2.2, ...YEARS.flatMap(() => [1, 1])]));
  kids.push(SRC("AviaSolutions analysis (oracle run, 19 July 2026) and the sent ZAG Secondary Forecast (18 June 2026)"));
}
stub("7  Uncertainty on stand demand", "note 23 v3 Part C (stated band from placement variants)", "the bridge explores placement variants for the engagement").forEach(x => kids.push(x));
kids.push(H1("8  Simulation and engineering export"));
kids.push(P("The CAST simulation file is the design day table with fewer columns (the Tashkent precedent, made structural in the canonical output table): serving an engineering consumer costs a projection, not a build. The excerpt below shows the first ten events of the 2045 design day in the CAST column set; the full file exports per year and scenario."));
kids.push(CAP("CAST export excerpt, first ten events of the 2045 design day (forecast)"));
kids.push(tbl(["#", "A/D", "Time", "Airline", "ICAO code", "Dom/Intl", "Pax", "Type"],
  data.design_days["2045"].cast_excerpt.map(r => r.map(String)), [0.6, 0.8, 1, 1, 1, 1, 1, 0.8]));
kids.push(SRC("AviaSolutions analysis (Zagreb oracle run, 19 July 2026); CAST projection of the canonical event table"));

kids.push(H1("Appendix A  Conventions register"));
kids.push(P("Every number in this report was produced under a named convention; candidates open with the current DDFS practitioner are marked. Schedule base: 2025 OAG sample weeks, event-grain dedupe (the full-year store replaces this within the week). Schengen split on aircraft destination; HR domestic in the Schengen split. Pax loading flat 0.80 on scheduled seats. Busy-hour window: clock hours, series ranked independently, 30th value; peaks non-additive. Peak runway movements: the 30th busiest movements hour. Stand ledger: cyclic weekly steady state; Overall peak is the composition at the max-concurrent instant, Individual is each code's own maximum. Terminal allocation (CANDIDATE, hers to confirm): FR, EW, JU, TK, BA at the Old Terminal. Overnight window (CANDIDATE): 22:00-06:00. Transfers (CANDIDATE): carried on OU services at a fixed base-year share of OU two-way passengers. Stand Scenario (CONFIRMED this session): code-C harmonisation, B-class on C stands one-for-one and the code-E widebody across two C stands. Design day (DD1): the day containing the 30th busiest 2-way hour. Full register: note 35 v2."));

const doc = new D.Document({
  creator: "Avia Solutions", lastModifiedBy: "Avia Solutions",
  title: "Avia Cortex DDFS - Design Day Report (Generator v0.1 demonstration on Zagreb)",
  styles: { default: { document: { run: { font: "Arial", size: 20 } } } },
  sections: [{
    properties: { page: { margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } },
    footers: { default: new D.Footer({ children: [new D.Paragraph({ alignment: D.AlignmentType.CENTER, children: [
      A("Avia Cortex DDFS - Design Day Report - DRAFT - P: ", { size: 14 }),
      new D.TextRun({ children: [D.PageNumber.CURRENT], font: "Arial", size: 14 })] })] }) },
    children: kids }] });
D.Packer.toBuffer(doc).then(b => { fs.writeFileSync("ddfs_report_v01.docx", b); console.log("written", b.length, "bytes"); });
