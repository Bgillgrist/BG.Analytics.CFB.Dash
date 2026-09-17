// Land areas are Census ALAND (square meters), matched to the map's 2017 FIPS.
// Sum actual land, never projected polygon area or logo locations.
function summarizeCountyOwnership(counties, landAreas) {
  const schools = new Map();
  const seen = new Set();
  for (const county of counties) {
    const owner = county.properties?.seed;
    if (!owner?.ownerTeamId) continue;
    const id = String(county.id).padStart(5, "0");
    if (seen.has(id)) throw new Error(`Duplicate county ${id} in the map.`);
    seen.add(id);
    const area = landAreas[id];
    if (!Number.isFinite(area) || area < 0) {
      throw new Error(`Land area is unavailable for county ${id}.`);
    }
    if (!schools.has(owner.ownerTeamId)) {
      schools.set(owner.ownerTeamId, {
        teamId: owner.ownerTeamId,
        name: owner.ownerTeam,
        logo: owner.ownerLogo || "",
        color: owner.ownerColor || "#0c2c50",
        counties: 0,
        landAreaM2: 0,
      });
    }
    const school = schools.get(owner.ownerTeamId);
    school.counties += 1;
    school.landAreaM2 += area;
  }
  return [...schools.values()];
}

function rankSchools(schools, metric, limit = 10) {
  if (!["counties", "landAreaM2"].includes(metric)) throw new Error("Unknown ranking metric.");
  const sorted = [...schools].sort((a, b) => b[metric] - a[metric] || a.name.localeCompare(b.name, "en"));
  let rank = 0;
  return sorted.slice(0, limit).map((school, index) => {
    if (index === 0 || school[metric] !== sorted[index - 1][metric]) rank = index + 1;
    return { ...school, rank };
  });
}
