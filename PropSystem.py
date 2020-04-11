import weakref

class NodeFactory(object):

    def __init__(self, propDef) -> None:
        super().__init__()
        self.propDef = weakref.proxy(propDef)

class VarFactory(NodeFactory):

    def __init__(self, propDef) -> None:
        super().__init__(propDef)
        self.params = {}

    def setNodeParam(self, param_name, param_value):
        self.params[param_name] = param_value


class PropertyDefinition(NodeFactory):

    def __init__(self, propDef) -> None:
        super().__init__(propDef)
        self


# def __init__(self) -> None:
    #     super().__init__()
    #     self.VAR =


class PlayerPropDef(PropertyDefinition):
    pass