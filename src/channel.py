from src.physical import PC_phy, Port_phy


class PC_cha(PC_phy):
    def __init__(self, name: str):
        self.name = name
        self._in_port = Port_cha(name + " in port")
        self._out_port = Port_cha(name + " out port")


class Port_cha(Port_phy):
    def __init__(self, name: str):
        super().__init__(name)
