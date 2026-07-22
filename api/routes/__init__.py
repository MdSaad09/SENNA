from api.routes.agents import router as agents
from api.routes.circuits import router as circuits
from api.routes.counterfactuals import router as counterfactuals
from api.routes.energy import router as energy
from api.routes.health import router as health
from api.routes.races import router as races
from api.routes.simulations import router as simulations
from api.routes.tyres import router as tyres

ALL = (health, circuits, races, simulations, counterfactuals, agents, energy, tyres)
