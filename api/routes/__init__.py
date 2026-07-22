# plain module imports — aliasing `router as simulations` here would shadow the
# submodules in the package namespace and break monkeypatching and reload alike
from api.routes import (
    agents,
    circuits,
    counterfactuals,
    energy,
    health,
    races,
    simulations,
    tyres,
)

ALL = (health.router, circuits.router, races.router, simulations.router,
       counterfactuals.router, agents.router, energy.router, tyres.router)
