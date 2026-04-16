// Mock data for all 5 panels — full static demonstration

export const MOCK_GOAL = "Maximize tensile strength (>45 MPa) while maintaining elongation at break above 180%, and minimizing processing cost. System should prefer bio-based additives where possible.";

export const MOCK_WEIGHTS = { strength: 0.50, flexibility: 0.35, cost: 0.15 };

export const MOCK_PAPERS = [
  {
    id: 'p1',
    title: 'Effect of Silica Nanoparticles on Tensile Properties of EPDM Rubber Composites',
    authors: 'Zhang et al.',
    year: 2023,
    type: 'paper',
    status: 'indexed',
    chunks: 18,
    insights: 3,
    relevance: 0.94,
    excerpt: 'Incorporation of functionalized silica at 5–15 phr significantly increases tensile modulus while preserving elongation at break above 200%...'
  },
  {
    id: 'p2',
    title: 'Epoxidized Natural Rubber Blends: Mechanical and Thermal Performance',
    authors: 'Patel & Krishnamurthy',
    year: 2022,
    type: 'paper',
    status: 'indexed',
    chunks: 24,
    insights: 5,
    relevance: 0.89,
    excerpt: 'ENR-50 blends with NBR at a 70:30 ratio demonstrated optimal balance of strength and flexibility under cyclic loading conditions...'
  },
  {
    id: 'tds1',
    title: 'LANXESS Vp.PBR 4010 — Technical Data Sheet',
    authors: 'LANXESS Corp.',
    year: 2024,
    type: 'tds',
    status: 'indexed',
    chunks: 8,
    insights: 0,
    relevance: 0.92,
    properties: { tensile_strength: 38.2, elongation: 420, density: 0.94, shore_a: 60 },
    excerpt: 'Polybutadiene rubber with high cis-1,4 content. Excellent low-temperature flexibility. Tensile: 38.2 MPa (ASTM D412)...'
  },
  {
    id: 'tds2',
    title: 'Kraton D1101 SBS Block Copolymer — TDS',
    authors: 'Kraton Performance Polymers',
    year: 2023,
    type: 'tds',
    status: 'indexed',
    chunks: 12,
    insights: 0,
    relevance: 0.87,
    properties: { tensile_strength: 32.5, elongation: 880, density: 0.93, shore_a: 41 },
    excerpt: 'Styrene-butadiene-styrene block copolymer. Outstanding tensile elongation (880%) with good UV resistance ...'
  },
  {
    id: 'p3',
    title: 'Cross-linking Density Effects on Mechanical Properties of Vulcanized NR',
    authors: 'Nguyen et al.',
    year: 2023,
    type: 'paper',
    status: 'processing',
    chunks: 0,
    insights: 0,
    relevance: 0.81,
    excerpt: 'Sulfur/CBS accelerator system at varying cross-link densities (0.2–1.8 mol/kg) was studied...'
  },
];

export const MOCK_INSIGHTS = [
  { id: 'i1', cause: 'Silica at 10 phr', effect: '+18% tensile strength, −5% elongation', confidence: 0.91, source: 'Zhang et al. 2023' },
  { id: 'i2', cause: 'ENR-50 / NBR 70:30 blend', effect: '+12% flex retention at −20°C, +9% strength', confidence: 0.87, source: 'Patel 2022' },
  { id: 'i3', cause: 'Plasticizer DOTP at 15 phr', effect: '+65% elongation, −8% tensile strength', confidence: 0.83, source: 'LANXESS TDS' },
  { id: 'i4', cause: 'CBS accelerator 1.5 phr', effect: 'Optimal cure rate, cross-link density 0.8 mol/kg', confidence: 0.79, source: 'Nguyen 2023' },
];

export const MOCK_EXPERIMENTS = [
  {
    id: 'exp-3a',
    rank: 1,
    iteration: 3,
    label: 'Config A',
    status: 'evaluated',
    composite_score: 0.832,
    scores: { strength: 0.91, flexibility: 0.74, cost: 0.68 },
    predicted: { tensile_strength: 46.8, elongation: 212, density: 0.96 },
    components: [
      { name: 'EPDM Base', pct: 60 },
      { name: 'ENR-50', pct: 25 },
      { name: 'Functionalized Silica', pct: 10 },
    ],
    additives: [{ name: 'CBS Accelerator', pct: 1.5 }, { name: 'Sulfur', pct: 2.0 }],
    process: { temperature: 160, cure_time: 18, pressure: 12 },
    hypothesis: 'Silica at 10 phr should bridge tensile gap while ENR-50 maintains elongation above threshold.',
  },
  {
    id: 'exp-3b',
    rank: 2,
    iteration: 3,
    label: 'Config B',
    status: 'evaluated',
    composite_score: 0.764,
    scores: { strength: 0.78, flexibility: 0.82, cost: 0.72 },
    predicted: { tensile_strength: 41.3, elongation: 248, density: 0.94 },
    components: [
      { name: 'EPDM Base', pct: 55 },
      { name: 'ENR-50', pct: 30 },
      { name: 'Functionalized Silica', pct: 8 },
    ],
    additives: [{ name: 'CBS Accelerator', pct: 1.2 }, { name: 'DOTP Plasticizer', pct: 5 }],
    process: { temperature: 155, cure_time: 20, pressure: 10 },
    hypothesis: 'Higher ENR-50 content and moderate plasticizer boosts elongation, trades some strength.',
  },
  {
    id: 'exp-3c',
    rank: 3,
    iteration: 3,
    label: 'Config C',
    status: 'evaluated',
    composite_score: 0.611,
    scores: { strength: 0.55, flexibility: 0.93, cost: 0.88 },
    predicted: { tensile_strength: 34.1, elongation: 310, density: 0.93 },
    components: [
      { name: 'EPDM Base', pct: 45 },
      { name: 'Kraton D1101', pct: 35 },
      { name: 'ENR-50', pct: 15 },
    ],
    additives: [{ name: 'DOTP Plasticizer', pct: 10 }],
    process: { temperature: 150, cure_time: 22, pressure: 9 },
    hypothesis: 'Kraton blend maximizes elongation but tensile strength falls below the 45 MPa target.',
  },
];

export const MOCK_TREND_DATA = [
  { iter: 1, strength: 0.52, flexibility: 0.61, composite: 0.55 },
  { iter: 2, strength: 0.69, flexibility: 0.70, composite: 0.69 },
  { iter: 3, strength: 0.91, flexibility: 0.74, composite: 0.83 },
];

export const MOCK_DECISION_REASONING = `**Config A** achieved the highest composite score of <strong>0.832</strong> across iteration 3.

Tensile strength prediction of <strong>46.8 MPa</strong> satisfies the primary goal threshold (>45 MPa). The 10 phr functionalized silica addition aligns with findings from <span class="citation-tds">[LANXESS TDS / Zhang 2023]</span> which showed +18% tensile gain at that concentration. ENR-50 at 25% preserved elongation at 212% — marginally above the 180% minimum.

Config B showed superior flexibility (elongation 248%) but tensile prediction of 41.3 MPa falls short of goal. Config C's cost efficiency is excellent but misses the strength target by −26%.

The CBS/sulfur cure system at 160°C/18 min is consistent with optimal cross-link densities (0.8 mol/kg) reported by <span class="citation-paper">[Nguyen et al. 2023]</span>.`;

export const MOCK_NEXT_HYPOTHESIS = `Iteration 4 will refine Config A: increase functionalized silica to 12 phr (testing upper bound of Zhang curve), reduce ENR-50 to 20% to mitigate cost, and add TESPT coupling agent at 1 phr to improve silica-rubber interfacial bonding. Expected tensile gain: +3–5 MPa. Elongation expected to drop to ~195% — still above threshold.`;

export const LOOP_STEPS = ['Retrieve', 'Extract', 'Generate', 'Evaluate', 'Decide'];
