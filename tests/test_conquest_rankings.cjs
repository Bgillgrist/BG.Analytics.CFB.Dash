// Run with: node --test tests/test_conquest_rankings.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/utils/conquest_rankings.js'), 'utf8');
const { summarizeCountyOwnership, rankSchools } = vm.runInNewContext(
  source + '\n({ summarizeCountyOwnership, rankSchools })'
);
const areas = JSON.parse(fs.readFileSync(path.join(__dirname, '../app/assets/conquest_county_land_2017.json'))).land_area_m2;
const owner = (id, name = id) => ({ ownerTeamId: id, ownerTeam: name, ownerLogo: `data:image/png;base64,${id}`,
  ownerColor: '#112233', logoGroupKey: 'conference:SEC' });
const county = (id, seed) => ({ id, properties: { seed } });

test('counts counties once and combines every territory held by the current owner', () => {
  const rows = summarizeCountyOwnership([
    county('01001', { ...owner('a'), seedTeamId: 'original-school-a' }),
    county('01003', { ...owner('a'), seedTeamId: 'conquered-school-b' }),
    county('01005', owner('b')),
    county('01007', null),
  ], { '01001': 100, '01003': 200, '01005': 400 });
  assert.equal(rows.length, 2);
  assert.equal(rows[0].counties, 2);
  assert.equal(rows[0].landAreaM2, 300);
  assert.equal(rows[0].logo, 'data:image/png;base64,a');
  assert.equal(rows[1].counties, 1);
});

test('conference mode still ranks individual schools with their school logos', () => {
  const rows = summarizeCountyOwnership([county(1001, owner('a')), county(1003, owner('b'))],
    { '01001': 100, '01003': 200 });
  assert.equal(rows.length, 2);
  assert.equal(rows[1].logo, 'data:image/png;base64,b');
});

test('Alaska uses real Census land area and may outrank a school holding more counties', () => {
  const rows = summarizeCountyOwnership([
    county('02290', owner('alaska')),
    county('01001', owner('alabama')), county('01003', owner('alabama')),
  ], areas);
  assert.equal(rankSchools(rows, 'counties')[0].teamId, 'alabama');
  assert.equal(rankSchools(rows, 'landAreaM2')[0].teamId, 'alaska');
  assert.equal(rows[0].landAreaM2, areas['02290']);
  assert.ok(rows[0].landAreaM2 / 2589988.110336 > 140000);
});

test('ties share competition rank, use alphabetical display order, and do not mutate totals', () => {
  const rows = [{ name: 'Zeta', counties: 4 }, { name: 'Beta', counties: 2 }, { name: 'Alpha', counties: 4 }];
  const sorted = rankSchools(rows, 'counties');
  assert.equal(JSON.stringify(sorted.map(r => [r.name, r.rank])), JSON.stringify([['Alpha', 1], ['Zeta', 1], ['Beta', 3]]));
  assert.equal(rows[0].name, 'Zeta');
  assert.equal(rows[0].rank, undefined);
});

test('a transfer updates both rankings and removes owners with no counties', () => {
  const before = summarizeCountyOwnership([county('01001', owner('a')), county('01003', owner('b'))], areas);
  const after = summarizeCountyOwnership([county('01001', owner('b')), county('01003', owner('b'))], areas);
  assert.equal(before.length, 2);
  assert.equal(after.length, 1);
  assert.equal(after[0].teamId, 'b');
  assert.equal(after[0].counties, 2);
  assert.equal(after[0].landAreaM2, before.reduce((total, r) => total + r.landAreaM2, 0));
});

test('missing or duplicate counties fail explicitly instead of publishing misleading totals', () => {
  assert.throws(() => summarizeCountyOwnership([county('99999', owner('a'))], areas), /unavailable/);
  assert.throws(() => summarizeCountyOwnership([county('01001', owner('a')), county('01001', owner('a'))], areas), /Duplicate/);
});

test('top ten preserves fewer owners and sorts by unrounded land area', () => {
  const rows = Array.from({ length: 15 }, (_, i) => ({ name: `School ${i}`, landAreaM2: 1000000 + i }));
  assert.equal(rankSchools(rows, 'landAreaM2').length, 10);
  assert.equal(rankSchools(rows, 'landAreaM2')[0].name, 'School 14');
  assert.equal(rankSchools(rows.slice(0, 3), 'landAreaM2').length, 3);
  assert.equal(rankSchools([], 'counties').length, 0);
});
