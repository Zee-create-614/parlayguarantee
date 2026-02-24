"""
NCAAB Team Name Mapper — Comprehensive D1 team name normalization.
Maps all known variations (abbreviations, mascots, city names) to canonical names.
Fuzzy matching fallback for unknown variations.
"""

from difflib import SequenceMatcher
from typing import Optional
import re

# Canonical name → list of known aliases (lowercase for matching)
# This covers 380+ D1 teams with common sportsbook variations
TEAM_ALIASES: dict[str, list[str]] = {
    # ACC
    "Boston College": ["boston college", "bc eagles", "boston col"],
    "Clemson": ["clemson", "clemson tigers"],
    "Duke": ["duke", "duke blue devils"],
    "Florida State": ["florida state", "florida st", "fsu", "fla state", "fsu seminoles"],
    "Georgia Tech": ["georgia tech", "ga tech", "gt yellow jackets", "georgia institute"],
    "Louisville": ["louisville", "louisville cardinals", "u of l"],
    "Miami (FL)": ["miami fl", "miami florida", "miami hurricanes", "miami (fl)", "miami oh", "miami"],
    "North Carolina": ["north carolina", "unc", "unc tar heels", "n carolina", "nc tar heels", "tar heels"],
    "NC State": ["nc state", "north carolina state", "n.c. state", "nc st", "ncsu", "wolfpack"],
    "Notre Dame": ["notre dame", "notre dame fighting irish", "nd fighting irish"],
    "Pittsburgh": ["pittsburgh", "pitt", "pitt panthers"],
    "Syracuse": ["syracuse", "cuse", "syracuse orange"],
    "Virginia": ["virginia", "uva", "virginia cavaliers", "va cavaliers"],
    "Virginia Tech": ["virginia tech", "va tech", "vt hokies", "hokies"],
    "Wake Forest": ["wake forest", "wake", "wake forest demon deacons"],
    "California": ["california", "cal", "cal bears", "california golden bears", "uc berkeley", "berkeley"],
    "SMU": ["smu", "southern methodist", "smu mustangs"],
    "Stanford": ["stanford", "stanford cardinal"],

    # Big 12
    "Arizona": ["arizona", "zona", "arizona wildcats", "u of a"],
    "Arizona State": ["arizona state", "arizona st", "asu", "asu sun devils"],
    "Baylor": ["baylor", "baylor bears"],
    "BYU": ["byu", "brigham young", "brigham young cougars"],
    "Central Florida": ["ucf", "central florida", "ucf knights", "central fla"],
    "Cincinnati": ["cincinnati", "cincy", "cincinnati bearcats", "uc bearcats"],
    "Colorado": ["colorado", "colorado buffaloes", "cu buffaloes", "cu buffs"],
    "Houston": ["houston", "houston cougars", "u of h"],
    "Iowa State": ["iowa state", "iowa st", "isu cyclones"],
    "Kansas": ["kansas", "ku", "kansas jayhawks", "ku jayhawks"],
    "Kansas State": ["kansas state", "kansas st", "k-state", "ksu wildcats"],
    "Oklahoma State": ["oklahoma state", "oklahoma st", "osu cowboys", "ok state"],
    "TCU": ["tcu", "texas christian", "tcu horned frogs"],
    "Texas Tech": ["texas tech", "ttu", "texas tech red raiders", "tt red raiders"],
    "Utah": ["utah", "utah utes", "u of u"],
    "West Virginia": ["west virginia", "wvu", "west va", "wv mountaineers"],

    # Big East
    "Butler": ["butler", "butler bulldogs"],
    "UConn": ["uconn", "connecticut", "uconn huskies", "connecticut huskies", "u conn"],
    "Creighton": ["creighton", "creighton bluejays"],
    "DePaul": ["depaul", "de paul", "depaul blue demons"],
    "Georgetown": ["georgetown", "georgetown hoyas"],
    "Marquette": ["marquette", "marquette golden eagles"],
    "Providence": ["providence", "providence friars"],
    "St. John's": ["st. john's", "st john's", "st johns", "saint john's", "st. john's red storm", "st johns red storm"],
    "Seton Hall": ["seton hall", "seton hall pirates"],
    "Villanova": ["villanova", "nova", "villanova wildcats"],
    "Xavier": ["xavier", "xavier musketeers"],

    # Big Ten
    "Illinois": ["illinois", "illinois fighting illini", "u of i", "illini"],
    "Indiana": ["indiana", "indiana hoosiers", "iu hoosiers"],
    "Iowa": ["iowa", "iowa hawkeyes"],
    "Maryland": ["maryland", "maryland terrapins", "terps"],
    "Michigan": ["michigan", "michigan wolverines", "u of m", "umich"],
    "Michigan State": ["michigan state", "michigan st", "msu spartans", "mich state", "mich st"],
    "Minnesota": ["minnesota", "minnesota golden gophers", "minn golden gophers"],
    "Nebraska": ["nebraska", "nebraska cornhuskers"],
    "Northwestern": ["northwestern", "northwestern wildcats"],
    "Ohio State": ["ohio state", "ohio st", "osu buckeyes", "the ohio state"],
    "Oregon": ["oregon", "oregon ducks"],
    "Penn State": ["penn state", "penn st", "psu nittany lions", "penn state nittany lions"],
    "Purdue": ["purdue", "purdue boilermakers"],
    "Rutgers": ["rutgers", "rutgers scarlet knights"],
    "UCLA": ["ucla", "ucla bruins"],
    "USC": ["usc", "southern california", "usc trojans", "southern cal"],
    "Washington": ["washington", "washington huskies", "uw huskies", "u of w"],
    "Wisconsin": ["wisconsin", "wisconsin badgers", "wisc badgers"],

    # SEC
    "Alabama": ["alabama", "bama", "alabama crimson tide", "crimson tide"],
    "Arkansas": ["arkansas", "arkansas razorbacks", "razorbacks"],
    "Auburn": ["auburn", "auburn tigers"],
    "Florida": ["florida", "florida gators", "uf gators"],
    "Georgia": ["georgia", "georgia bulldogs", "uga bulldogs"],
    "Kentucky": ["kentucky", "uk wildcats", "kentucky wildcats"],
    "LSU": ["lsu", "louisiana state", "lsu tigers"],
    "Mississippi State": ["mississippi state", "mississippi st", "miss state", "miss st", "msu bulldogs"],
    "Missouri": ["missouri", "mizzou", "missouri tigers"],
    "Oklahoma": ["oklahoma", "ou", "oklahoma sooners", "ou sooners"],
    "Ole Miss": ["ole miss", "mississippi", "miss rebels", "ole miss rebels"],
    "South Carolina": ["south carolina", "s carolina", "sc gamecocks", "south carolina gamecocks"],
    "Tennessee": ["tennessee", "tennessee volunteers", "vols", "ut vols"],
    "Texas": ["texas", "texas longhorns", "ut longhorns"],
    "Texas A&M": ["texas a&m", "texas am", "tamu", "texas a&m aggies", "tamu aggies"],
    "Vanderbilt": ["vanderbilt", "vandy", "vanderbilt commodores"],

    # AAC
    "Charlotte": ["charlotte", "charlotte 49ers"],
    "East Carolina": ["east carolina", "ecu", "ecu pirates", "e carolina"],
    "FAU": ["fau", "florida atlantic", "florida atlantic owls"],
    "Memphis": ["memphis", "memphis tigers"],
    "North Texas": ["north texas", "unt", "unt mean green", "n texas"],
    "Rice": ["rice", "rice owls"],
    "South Florida": ["south florida", "usf", "usf bulls", "s florida"],
    "Temple": ["temple", "temple owls"],
    "Tulane": ["tulane", "tulane green wave"],
    "Tulsa": ["tulsa", "tulsa golden hurricane"],
    "UAB": ["uab", "alabama-birmingham", "uab blazers"],
    "UTSA": ["utsa", "ut san antonio", "utsa roadrunners"],
    "Wichita State": ["wichita state", "wichita st", "wichita state shockers"],

    # Mountain West
    "Air Force": ["air force", "air force falcons"],
    "Boise State": ["boise state", "boise st", "boise state broncos"],
    "Colorado State": ["colorado state", "colorado st", "csu rams"],
    "Fresno State": ["fresno state", "fresno st", "fresno state bulldogs"],
    "Nevada": ["nevada", "nevada wolf pack", "unr"],
    "New Mexico": ["new mexico", "unm", "unm lobos", "new mexico lobos"],
    "San Diego State": ["san diego state", "sdsu", "sdsu aztecs"],
    "San Jose State": ["san jose state", "sjsu", "san jose st", "san jose st spartans", u"san jos\u00e9 st spartans", "san jose state spartans"],
    "UNLV": ["unlv", "nevada-las vegas", "unlv rebels"],
    "Utah State": ["utah state", "utah st", "utah state aggies"],
    "Wyoming": ["wyoming", "wyoming cowboys"],

    # Pac-12 remnants / WCC
    "Gonzaga": ["gonzaga", "gonzaga bulldogs", "zags"],
    "Saint Mary's": ["saint mary's", "st mary's", "st. mary's", "saint marys", "st marys"],
    "San Francisco": ["san francisco", "usf dons", "sf dons"],
    "Santa Clara": ["santa clara", "santa clara broncos"],
    "Pepperdine": ["pepperdine", "pepperdine waves"],
    "Portland": ["portland", "portland pilots"],
    "Loyola Marymount": ["loyola marymount", "lmu", "lmu lions"],
    "Pacific": ["pacific", "pacific tigers"],

    # A-10
    "Dayton": ["dayton", "dayton flyers"],
    "Davidson": ["davidson", "davidson wildcats"],
    "Fordham": ["fordham", "fordham rams"],
    "George Mason": ["george mason", "gmu", "george mason patriots"],
    "George Washington": ["george washington", "gw", "gwu", "gw colonials"],
    "La Salle": ["la salle", "la salle explorers"],
    "Loyola Chicago": ["loyola chicago", "loyola-chicago", "loyola chi", "luc ramblers", "loyola (chi)", "loyola (chi) ramblers", "loyola chi ramblers"],
    "Massachusetts": ["massachusetts", "umass", "umass minutemen"],
    "Rhode Island": ["rhode island", "uri", "rhode island rams"],
    "Richmond": ["richmond", "richmond spiders"],
    "Saint Louis": ["saint louis", "st louis", "st. louis", "slu", "slu billikens"],
    "St. Bonaventure": ["st. bonaventure", "st bonaventure", "saint bonaventure", "bonnies"],
    "VCU": ["vcu", "virginia commonwealth", "vcu rams"],

    # Colonial / CAA
    "College of Charleston": ["college of charleston", "charleston", "cofc"],
    "Delaware": ["delaware", "delaware fightin blue hens"],
    "Drexel": ["drexel", "drexel dragons"],
    "Elon": ["elon", "elon phoenix"],
    "Hofstra": ["hofstra", "hofstra pride"],
    "James Madison": ["james madison", "jmu", "jmu dukes"],
    "Northeastern": ["northeastern", "northeastern huskies"],
    "Stony Brook": ["stony brook", "stony brook seawolves"],
    "Towson": ["towson", "towson tigers"],
    "UNC Wilmington": ["unc wilmington", "uncw", "wilmington"],
    "William & Mary": ["william & mary", "william and mary", "w&m"],

    # Ivy League
    "Brown": ["brown", "brown bears"],
    "Columbia": ["columbia", "columbia lions"],
    "Cornell": ["cornell", "cornell big red"],
    "Dartmouth": ["dartmouth", "dartmouth big green"],
    "Harvard": ["harvard", "harvard crimson"],
    "Penn": ["penn", "pennsylvania", "penn quakers"],
    "Princeton": ["princeton", "princeton tigers"],
    "Yale": ["yale", "yale bulldogs"],

    # MAAC
    "Canisius": ["canisius", "canisius golden griffins"],
    "Fairfield": ["fairfield", "fairfield stags"],
    "Iona": ["iona", "iona gaels"],
    "Manhattan": ["manhattan", "manhattan jaspers"],
    "Marist": ["marist", "marist red foxes"],
    "Niagara": ["niagara", "niagara purple eagles"],
    "Quinnipiac": ["quinnipiac", "quinnipiac bobcats"],
    "Rider": ["rider", "rider broncs"],
    "Saint Peter's": ["saint peter's", "st peter's", "st. peter's", "saint peters"],
    "Siena": ["siena", "siena saints"],

    # MAC
    "Akron": ["akron", "akron zips"],
    "Ball State": ["ball state", "ball st", "ball state cardinals"],
    "Bowling Green": ["bowling green", "bgsu", "bowling green falcons"],
    "Buffalo": ["buffalo", "buffalo bulls", "ub bulls"],
    "Central Michigan": ["central michigan", "cmu", "central mich", "cmu chippewas"],
    "Eastern Michigan": ["eastern michigan", "emu", "eastern mich", "emu eagles"],
    "Kent State": ["kent state", "kent st", "kent state golden flashes"],
    "Miami (OH)": ["miami oh", "miami ohio", "miami (oh)", "miami redhawks"],
    "Northern Illinois": ["northern illinois", "niu", "niu huskies", "n illinois"],
    "Ohio": ["ohio", "ohio bobcats", "ohio university"],
    "Toledo": ["toledo", "toledo rockets"],
    "Western Michigan": ["western michigan", "wmu", "western mich", "wmu broncos"],

    # Missouri Valley
    "Bradley": ["bradley", "bradley braves"],
    "Drake": ["drake", "drake bulldogs"],
    "Evansville": ["evansville", "evansville aces"],
    "Illinois State": ["illinois state", "illinois st", "isu redbirds"],
    "UIC": ["uic", "illinois-chicago", "illinois chicago", "uic flames", "ui chicago"],
    "Indiana State": ["indiana state", "indiana st", "indiana state sycamores"],
    "Missouri State": ["missouri state", "missouri st", "mo state", "missouri state bears"],
    "Northern Iowa": ["northern iowa", "uni", "uni panthers"],
    "Southern Illinois": ["southern illinois", "siu", "siu salukis", "s illinois"],
    "Valparaiso": ["valparaiso", "valpo", "valparaiso beacons"],

    # Conference USA
    "FIU": ["fiu", "florida international", "fiu panthers", "florida int'l", "florida int'l golden panthers"],
    "Jacksonville State": ["jacksonville state", "jacksonville st", "jax state"],
    "Kennesaw State": ["kennesaw state", "kennesaw st", "kennesaw"],
    "Liberty": ["liberty", "liberty flames"],
    "Louisiana Tech": ["louisiana tech", "la tech", "louisiana tech bulldogs"],
    "Middle Tennessee": ["middle tennessee", "mtsu", "middle tenn", "mid tennessee"],
    "New Mexico State": ["new mexico state", "new mexico st", "nmsu", "nm state"],
    "Sam Houston State": ["sam houston", "sam houston state", "shsu", "sam houston st"],
    "Western Kentucky": ["western kentucky", "wku", "w kentucky"],

    # Sun Belt
    "Appalachian State": ["appalachian state", "appalachian st", "app state", "app st"],
    "Arkansas State": ["arkansas state", "arkansas st", "a-state"],
    "Coastal Carolina": ["coastal carolina", "coastal", "ccu chanticleers"],
    "Georgia Southern": ["georgia southern", "ga southern"],
    "Georgia State": ["georgia state", "ga state", "gsu panthers"],
    "James Madison": ["james madison", "jmu"],
    "Louisiana": ["louisiana", "louisiana ragin cajuns", "ull", "ul lafayette", "louisiana-lafayette"],
    "Louisiana-Monroe": ["louisiana-monroe", "ulm", "la-monroe", "ul monroe", "louisiana monroe"],
    "Marshall": ["marshall", "marshall thundering herd"],
    "Old Dominion": ["old dominion", "odu", "old dominion monarchs"],
    "South Alabama": ["south alabama", "usa jaguars", "s alabama"],
    "Southern Miss": ["southern miss", "southern mississippi", "usm", "usm golden eagles"],
    "Texas State": ["texas state", "texas st", "txst"],
    "Troy": ["troy", "troy trojans"],

    # America East
    "Albany": ["albany", "albany great danes", "suny albany"],
    "Binghamton": ["binghamton", "binghamton bearcats"],
    "Hartford": ["hartford", "hartford hawks"],
    "Maine": ["maine", "maine black bears"],
    "New Hampshire": ["new hampshire", "unh", "unh wildcats"],
    "UMBC": ["umbc", "maryland-baltimore county"],
    "UMass Lowell": ["umass lowell", "mass lowell"],
    "Vermont": ["vermont", "vermont catamounts"],

    # Atlantic Sun
    "Bellarmine": ["bellarmine", "bellarmine knights"],
    "Central Arkansas": ["central arkansas", "uca", "uca bears"],
    "Eastern Kentucky": ["eastern kentucky", "eku", "e kentucky"],
    "Florida Gulf Coast": ["florida gulf coast", "fgcu", "fgcu eagles"],
    "Jacksonville": ["jacksonville", "jacksonville dolphins", "ju dolphins"],
    "Lipscomb": ["lipscomb", "lipscomb bisons"],
    "North Alabama": ["north alabama", "una", "una lions"],
    "North Florida": ["north florida", "unf", "unf ospreys"],
    "Stetson": ["stetson", "stetson hatters"],

    # Big Sky
    "Eastern Washington": ["eastern washington", "ewu", "e washington"],
    "Idaho": ["idaho", "idaho vandals"],
    "Idaho State": ["idaho state", "idaho st", "isu bengals"],
    "Montana": ["montana", "montana grizzlies"],
    "Montana State": ["montana state", "montana st", "msu bobcats"],
    "Northern Arizona": ["northern arizona", "nau", "nau lumberjacks"],
    "Northern Colorado": ["northern colorado", "unc bears", "unco", "n colorado", "n colorado bears"],
    "Portland State": ["portland state", "portland st"],
    "Sacramento State": ["sacramento state", "sac state", "sac st"],
    "Weber State": ["weber state", "weber st", "weber state wildcats"],

    # Big South
    "Campbell": ["campbell", "campbell fighting camels"],
    "Charleston Southern": ["charleston southern", "csu buccaneers"],
    "Gardner-Webb": ["gardner-webb", "gardner webb", "gwu runnin bulldogs"],
    "High Point": ["high point", "high point panthers"],
    "Longwood": ["longwood", "longwood lancers"],
    "Presbyterian": ["presbyterian", "presbyterian blue hose"],
    "Radford": ["radford", "radford highlanders"],
    "UNC Asheville": ["unc asheville", "unca", "asheville"],
    "Winthrop": ["winthrop", "winthrop eagles"],

    # Horizon League
    "Cleveland State": ["cleveland state", "cleveland st", "csu vikings"],
    "Detroit Mercy": ["detroit mercy", "detroit", "udm titans"],
    "Green Bay": ["green bay", "uw-green bay", "uwgb"],
    "IUPUI": ["iupui", "iu indianapolis"],
    "Milwaukee": ["milwaukee", "uw-milwaukee", "uwm panthers"],
    "Northern Kentucky": ["northern kentucky", "nku", "nku norse"],
    "Oakland": ["oakland", "oakland golden grizzlies"],
    "Purdue Fort Wayne": ["purdue fort wayne", "pfw", "fort wayne"],
    "Robert Morris": ["robert morris", "rmu colonials"],
    "Wright State": ["wright state", "wright st"],
    "Youngstown State": ["youngstown state", "youngstown st", "ysu penguins"],

    # Mid-American / OVC / Southland / MEAC / SWAC — abbreviated for space
    "Murray State": ["murray state", "murray st"],
    "Morehead State": ["morehead state", "morehead st"],
    "Austin Peay": ["austin peay", "apsu", "austin peay governors"],
    "Tennessee State": ["tennessee state", "tennessee st", "tsu tigers"],
    "Tennessee Tech": ["tennessee tech", "ttu golden eagles"],
    "Southeast Missouri State": ["southeast missouri", "semo", "se missouri", "southeast missouri state"],
    "UT Martin": ["ut martin", "tennessee-martin"],
    "Belmont": ["belmont", "belmont bruins"],
    "Eastern Illinois": ["eastern illinois", "eiu", "eiu panthers"],
    "SIU Edwardsville": ["siu edwardsville", "siue", "siue cougars", "siu-edwardsville"],
    "NJIT": ["njit", "njit highlanders", "new jersey tech"],
    "UTEP": ["utep", "utep miners", "texas-el paso", "texas el paso"],
    "Lindenwood": ["lindenwood", "lindenwood lions"],
    "Little Rock": ["little rock", "ualr", "ua little rock", "ualr trojans", "arkansas little rock", "arkansas-little rock"],
    "Lamar": ["lamar", "lamar cardinals"],
    "McNeese": ["mcneese", "mcneese state", "mcneese cowboys"],
    "Nicholls": ["nicholls", "nicholls state", "nicholls colonels"],
    "Northwestern State": ["northwestern state", "nw state", "northwestern st"],
    "Southeastern Louisiana": ["southeastern louisiana", "se louisiana", "selu"],
    "Stephen F. Austin": ["stephen f. austin", "sfa", "stephen f austin", "sfa lumberjacks"],
    "Texas A&M-Corpus Christi": ["texas a&m-corpus christi", "tamucc", "a&m corpus christi", "texas a&m-cc", "t a&m corpus christi", "texas a&m corpus christi"],
    "Houston Christian": ["houston christian", "houston baptist", "hbu", "hcu"],
    "Incarnate Word": ["incarnate word", "uiw", "uiw cardinals"],
    "Alcorn State": ["alcorn state", "alcorn", "alcorn st"],
    "Alabama A&M": ["alabama a&m", "aamu", "alabama am"],
    "Alabama State": ["alabama state", "alabama st", "asu hornets"],
    "Bethune-Cookman": ["bethune-cookman", "bethune cookman", "bcu wildcats"],
    "Coppin State": ["coppin state", "coppin st"],
    "Delaware State": ["delaware state", "delaware st", "dsu hornets"],
    "Florida A&M": ["florida a&m", "famu", "famu rattlers"],
    "Grambling": ["grambling", "grambling state", "grambling st"],
    "Hampton": ["hampton", "hampton pirates"],
    "Howard": ["howard", "howard bison"],
    "Jackson State": ["jackson state", "jackson st", "jsu tigers"],
    "Maryland-Eastern Shore": ["maryland-eastern shore", "umes", "md eastern shore"],
    "Mississippi Valley State": ["mississippi valley state", "mvsu", "miss valley"],
    "Morgan State": ["morgan state", "morgan st"],
    "Norfolk State": ["norfolk state", "norfolk st", "nsu spartans"],
    "North Carolina A&T": ["north carolina a&t", "nc a&t", "ncat aggies"],
    "North Carolina Central": ["north carolina central", "nccu", "nc central"],
    "Prairie View A&M": ["prairie view", "prairie view a&m", "pvamu"],
    "Savannah State": ["savannah state", "savannah st"],
    "South Carolina State": ["south carolina state", "sc state", "scsu bulldogs"],
    "Southern": ["southern", "southern university", "southern jaguars", "southern u"],
    "Texas Southern": ["texas southern", "txso", "tsu tigers"],

    # Patriot League
    "American": ["american", "american university", "au eagles"],
    "Army": ["army", "army west point", "army black knights"],
    "Boston University": ["boston university", "bu", "bu terriers"],
    "Bucknell": ["bucknell", "bucknell bison"],
    "Colgate": ["colgate", "colgate raiders"],
    "Holy Cross": ["holy cross", "holy cross crusaders"],
    "Lafayette": ["lafayette", "lafayette leopards"],
    "Lehigh": ["lehigh", "lehigh mountain hawks"],
    "Loyola Maryland": ["loyola maryland", "loyola md", "loyola (md)"],
    "Navy": ["navy", "navy midshipmen"],

    # Southern Conference
    "Chattanooga": ["chattanooga", "utc mocs", "ut chattanooga", "chattanooga mocs"],
    "East Tennessee State": ["east tennessee state", "etsu", "etsu buccaneers", "e tennessee st"],
    "Furman": ["furman", "furman paladins"],
    "Mercer": ["mercer", "mercer bears"],
    "Samford": ["samford", "samford bulldogs"],
    "The Citadel": ["the citadel", "citadel", "citadel bulldogs"],
    "UNC Greensboro": ["unc greensboro", "uncg", "greensboro"],
    "VMI": ["vmi", "virginia military", "vmi keydets"],
    "Western Carolina": ["western carolina", "wcu", "w carolina"],
    "Wofford": ["wofford", "wofford terriers"],

    # Summit League
    "Denver": ["denver", "denver pioneers"],
    "Kansas City": ["kansas city", "umkc", "umkc kangaroos"],
    "North Dakota": ["north dakota", "und", "north dakota fighting hawks"],
    "North Dakota State": ["north dakota state", "ndsu", "ndsu bison", "n dakota st", "north dakota st"],
    "Omaha": ["omaha", "nebraska-omaha", "uno mavericks"],
    "Oral Roberts": ["oral roberts", "oru", "oral roberts golden eagles"],
    "South Dakota": ["south dakota", "usd", "usd coyotes", "s dakota"],
    "South Dakota State": ["south dakota state", "sdsu jackrabbits", "s dakota st", "south dakota st"],
    "Western Illinois": ["western illinois", "wiu", "w illinois"],

    # WAC
    "Abilene Christian": ["abilene christian", "acu", "acu wildcats"],
    "California Baptist": ["california baptist", "cal baptist", "cbu lancers"],
    "Grand Canyon": ["grand canyon", "gcu", "gcu antelopes"],
    "Seattle": ["seattle", "seattle university", "seattle redhawks", "seattle u"],
    "Southern Utah": ["southern utah", "suu", "suu thunderbirds"],
    "Stephen F. Austin": ["stephen f. austin", "sfa", "sfa lumberjacks"],
    "Tarleton State": ["tarleton state", "tarleton", "tarleton st"],
    "UT Arlington": ["ut arlington", "uta", "uta mavericks", "texas-arlington", "ut-arlington"],
    "Utah Valley": ["utah valley", "uvu", "utah valley wolverines"],

    # Additional notable teams
    "Gonzaga": ["gonzaga", "gonzaga bulldogs", "zags"],
    "Saint Mary's": ["saint mary's", "st mary's", "st. mary's", "saint marys"],
    "Wichita State": ["wichita state", "wichita st"],
    "Loyola Chicago": ["loyola chicago", "loyola-chicago", "loyola chi"],
    "San Diego": ["san diego", "san diego toreros"],
    "Duquesne": ["duquesne", "duquesne dukes"],
    "St. Joseph's": ["st. joseph's", "saint joseph's", "st josephs", "saint josephs", "st. joe's"],
    "Wagner": ["wagner", "wagner seahawks"],
    "Long Beach State": ["long beach state", "long beach st", "lbsu"],
    "UC Davis": ["uc davis", "california-davis"],
    "UC Irvine": ["uc irvine", "california-irvine", "uci"],
    "UC Riverside": ["uc riverside", "california-riverside", "ucr"],
    "UC San Diego": ["uc san diego", "ucsd", "california-san diego"],
    "UC Santa Barbara": ["uc santa barbara", "ucsb", "california-santa barbara"],
    "Hawaii": ["hawaii", "hawai'i", "hawaii rainbow warriors"],
    "Cal Poly": ["cal poly", "cal poly slo"],
    "Cal State Fullerton": ["cal state fullerton", "csuf", "fullerton"],
    "Cal State Bakersfield": ["cal state bakersfield", "csub", "bakersfield"],
    "Cal State Northridge": ["cal state northridge", "csun", "northridge"],
    "CS Sacramento": ["cs sacramento", "sacramento st", "sacramento state"],

    # Northeast / Southland / Misc
    "Fairleigh Dickinson": ["fairleigh dickinson", "fdu", "fdu knights"],
    "LIU": ["liu", "long island", "long island university", "liu sharks"],
    "Merrimack": ["merrimack", "merrimack warriors"],
    "Mount St. Mary's": ["mount st. mary's", "mt st mary's", "mount st marys", "the mount"],
    "Sacred Heart": ["sacred heart", "sacred heart pioneers"],
    "St. Francis (PA)": ["st. francis pa", "saint francis pa", "st francis pa"],
    "St. Francis Brooklyn": ["st. francis brooklyn", "sfbk", "st francis brooklyn"],
    "Central Connecticut": ["central connecticut", "ccsu", "central conn"],
    "Le Moyne": ["le moyne", "lemoyne"],
    "Stonehill": ["stonehill", "stonehill skyhawks"],
    "Chicago State": ["chicago state", "chicago st"],
    "Texas A&M-Commerce": ["texas a&m-commerce", "tamuc", "a&m commerce", "east texas a&m", "texas a&m commerce"],
    "Monmouth": ["monmouth", "monmouth hawks"],
    "Mercyhurst": ["mercyhurst", "mercyhurst lakers"],
    "Queens University": ["queens university", "queens university royals", "queens nc"],
    "St. Thomas (MN)": ["st. thomas", "st thomas", "st. thomas (mn)", "st thomas (mn)", "st. thomas mn", "st. thomas tommies"],
    "Arkansas-Pine Bluff": ["arkansas-pine bluff", "arkansas pine bluff", "uapb", "uapb golden lions"],
    "Prairie View A&M": ["prairie view a&m", "prairie view", "pvamu", "prairie view panthers"],
    "West Georgia": ["west georgia", "west georgia wolves"],
    "SC Upstate": ["south carolina upstate", "sc upstate", "usc upstate"],
    "New Haven": ["new haven", "new haven chargers"],
    "College of Charleston": ["college of charleston", "charleston", "charleston cougars", "cofc"],
    "Incarnate Word": ["incarnate word", "uiw", "uiw cardinals"],
    "New Orleans": ["new orleans", "uno", "uno privateers", "new orleans privateers"],
    "CSU Northridge": ["csu northridge", "cal state northridge", "csun", "csun matadors"],
    "CSU Bakersfield": ["csu bakersfield", "cal state bakersfield", "csub", "csub roadrunners"],
    "CSU Fullerton": ["csu fullerton", "cal state fullerton", "csuf", "csuf titans"],
    "Long Beach State": ["long beach state", "long beach st", "lbsu", "lbsu 49ers"],
    "Southeast Missouri State": ["southeast missouri state", "semo", "se missouri state", "se missouri st"],
    "Presbyterian": ["presbyterian", "presbyterian blue hose"],
    "Norfolk State": ["norfolk state", "norfolk st", "nsu spartans", "norfolk st spartans"],
    "South Carolina State": ["south carolina state", "sc state", "scsu bulldogs", "south carolina st"],
    "Georgia State": ["georgia state", "ga state", "gsu panthers", "georgia st"],
    "James Madison": ["james madison", "jmu", "jmu dukes", "james madison dukes"],
    "Utah Valley": ["utah valley", "uvu", "uvu wolverines", "utah valley wolverines"],
    "UT Rio Grande Valley": ["ut rio grande valley", "utrgv", "texas-rio grande valley"],
    "Dixie State": ["dixie state", "utah tech"],
    "Utah Tech": ["utah tech", "dixie state"],
}

# Build reverse lookup: lowercase alias → canonical name
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in TEAM_ALIASES.items():
    _ALIAS_TO_CANONICAL[canonical.lower()] = canonical
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical


def _clean(name: str) -> str:
    """Normalize a team name for lookup."""
    name = name.strip()
    # Remove common suffixes that sportsbooks add
    for suffix in [" (home)", " (away)", " spread", " total", " moneyline"]:
        name = name.replace(suffix, "")
    # Normalize unicode
    name = name.replace("\u2019", "'").replace("\u2018", "'")
    # Normalize parenthesized abbreviations: "Loyola (Chi)" → "Loyola Chi"
    name = re.sub(r'\((\w+)\)', r'\1', name)
    # Normalize hyphens to spaces (but keep in aliases too for exact match)
    # Don't do this here — some teams have hyphens in canonical names
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


# Common mascot names to strip for matching
_MASCOTS = {
    "hawks", "eagles", "tigers", "bulldogs", "bears", "wildcats", "panthers",
    "cougars", "huskies", "spartans", "warriors", "knights", "broncos",
    "wolves", "owls", "cardinals", "falcons", "lions", "bobcats", "rams",
    "hornets", "bison", "aggies", "mustangs", "rockets", "flyers", "friars",
    "hoyas", "retrievers", "highlanders", "pioneers", "privateers", "flames",
    "beacons", "matadors", "49ers", "roadrunners", "lumberjacks", "vandals",
    "catamounts", "islanders", "cowboys", "redhawks", "trojans", "miners",
    "dukes", "ramblers", "sharks", "lakers", "royals", "wolverines",
    "mavericks", "blue hose", "golden panthers", "jackrabbits", "fighting hawks",
    "golden lions", "chargers", "tommies", "aztecs", "titans",
}

def _expand_abbreviations(name: str) -> str:
    """Expand common abbreviations in team names."""
    # Order matters — do specific patterns first
    replacements = [
        (r"\bint'l\b", "international"),
        (r"\bintl\b", "international"),
        (r"\bn\.\s*", "north "),
        (r"\bs\.\s*", "south "),
        (r"\be\.\s*", "east "),
        (r"\bw\.\s*", "west "),
        (r"\bcsu\b", "cal state"),
        (r"\bse\b", "southeast"),
        (r"\bumkc\b", "kansas city"),
        (r"\bt a&m\b", "texas a&m"),
        # "St" at end or before mascot = "State" (but "St." at start = "Saint")
    ]
    result = name.lower()
    for pat, rep in replacements:
        result = re.sub(pat, rep, result)

    # Handle "St" → "State" when it appears after a place name (not at start)
    # e.g., "Georgia St" → "Georgia State", but "St. John's" stays
    result = re.sub(r'(\w)\s+st\b(?!\.\s*\w)', r'\1 state', result)

    return result


def _strip_mascot(name: str) -> str:
    """Remove mascot names from end of team name."""
    words = name.lower().split()
    # Try stripping 1, 2, or 3 words from end
    for drop in range(1, min(4, len(words))):
        tail = " ".join(words[-drop:])
        if tail in _MASCOTS:
            return " ".join(words[:-drop])
    return name.lower()


def normalize_team(name: str) -> str:
    """
    Map a team name to its canonical form.
    Returns the canonical name if found, otherwise returns the cleaned input.
    """
    cleaned = _clean(name)
    lower = cleaned.lower()

    # Direct lookup
    if lower in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[lower]

    # Try with abbreviation expansion FIRST (before partial matching)
    expanded = _expand_abbreviations(lower)
    if expanded != lower:
        if expanded in _ALIAS_TO_CANONICAL:
            return _ALIAS_TO_CANONICAL[expanded]

    # Try without trailing mascot word (e.g. "Duke Blue Devils" → try "Duke Blue" → "Duke")
    # Use expanded form for partial matching
    for form in [expanded, lower] if expanded != lower else [lower]:
        words = form.split()
        for i in range(len(words), 0, -1):
            partial = " ".join(words[:i])
            if partial in _ALIAS_TO_CANONICAL:
                return _ALIAS_TO_CANONICAL[partial]

    # Try expanded partial (already done above)

    # Try mascot stripping
    stripped = _strip_mascot(lower)
    if stripped != lower and stripped in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[stripped]

    # Try mascot stripping + expansion
    stripped_exp = _expand_abbreviations(stripped)
    if stripped_exp in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[stripped_exp]
    # Partial
    sw = stripped_exp.split()
    for i in range(len(sw), 0, -1):
        partial = " ".join(sw[:i])
        if partial in _ALIAS_TO_CANONICAL:
            return _ALIAS_TO_CANONICAL[partial]

    # Fuzzy match fallback (high threshold to avoid false matches)
    return fuzzy_match(cleaned) or cleaned


def fuzzy_match(name: str, threshold: float = 0.88) -> Optional[str]:
    """Fuzzy match a name against all known aliases. Returns canonical name or None."""
    lower = name.lower()
    best_score = 0.0
    best_canonical = None

    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        score = SequenceMatcher(None, lower, alias).ratio()
        if score > best_score:
            best_score = score
            best_canonical = canonical

    if best_score >= threshold:
        return best_canonical
    return None


def are_same_team(name1: str, name2: str) -> bool:
    """Check if two team name strings refer to the same team."""
    return normalize_team(name1) == normalize_team(name2)


if __name__ == "__main__":
    # Quick test
    tests = [
        "UConn", "Connecticut", "UCONN Huskies",
        "Duke Blue Devils", "Duke",
        "NC State Wolfpack", "North Carolina State",
        "Michigan St", "Michigan State Spartans",
        "St. John's Red Storm", "Saint John's",
    ]
    for t in tests:
        print(f"  {t:30s} → {normalize_team(t)}")
