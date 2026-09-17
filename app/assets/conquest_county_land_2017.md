# Conquest county land areas

`conquest_county_land_2017.json` contains **ALAND** (land area in square meters)
keyed by five-digit county FIPS/GEOID. Water area is excluded. The 3,142 records
cover the 50 states and DC, including county equivalents such as Alaska boroughs
and independent cities. Puerto Rico and other territories are excluded, matching
the conquest map.

Source: [2017 U.S. Census National Counties Gazetteer](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2017_Gazetteer/2017_Gaz_counties_national.zip).
Read `2017_Gaz_counties_national.txt` as a tab-separated Latin-1 file, keep `GEOID`
and integer `ALAND`, and exclude state prefixes 60, 66, 69, 72, and 78.

The vintage deliberately matches [us-atlas v3's 2017 county boundaries](https://github.com/topojson/us-atlas),
which the dashboard already uses. Every displayed county FIPS was checked against
the land-area file. Do not substitute a newer Gazetteer without also updating and
checking the map boundaries (county definitions change).

The rankings sum land by each county's **current school owner**, including all
disconnected territories. School ownership is used even in Conference display
mode. No area is inferred from map pixels or the Alaska/Hawaii inset scale.
Totals are divided by 2,589,988.110336 to display square miles, and rounded only
for presentation. Ties share a competition rank; alphabetical order breaks display
ties within the top ten rows. Schools with no territory are omitted.

This bundled file requires no additional network request when creating slides.
