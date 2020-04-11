import random



class BattleUnit(object):

    def __init__(self) -> None:
        super().__init__()
        self.strength = 1


    def calucHurt(self, attacker, skillStrength):
        # 是否暴击
        dr = self.doRoll(attacker)
        if dr:
            if self.isPlayer():
                return skillStrength * attacker.strength * self.equipHurtFactor() * 2.0
            else:
                return skillStrength * attacker.strength * 2.0
        else:
            if self.isPlayer():
                return skillStrength * attacker.strength * self.equipHurtFactor() * 1.0
            else:
                return skillStrength * attacker.strength * 1.0

    def doRoll(self, attacker):
        dr = random.random() < (self.level - attacker.level) / self.level
        return dr


class Equip(object):

    def __init__(self) -> None:
        super().__init__()
        self.equipList = []

    def equipHurtFactor(self):
        return 1 + sum([equip.strength for equip in self.equipList])

class Entity(object):

    def __init__(self) -> None:
        super().__init__()
        self.level = 1


class Player(Entity, Equip, BattleUnit):
    def isPlayer(self):
        return True

class Monster(Entity, Equip, BattleUnit):
    def isPlayer(self):
        return False

## test

import unittest

class MyTestCase(unittest.TestCase):

    def setUp(self):
        pass

    def test_something1(self):
        player = Player()
        monster = Monster()
        hurt = monster.calucHurt(player, 10)
        print("hurt", hurt)
        self.assertIn(hurt, [10, 20])

    def test_something2(self):
        pass

    def test_something3(self):
        self.assertEqual(True, True)

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()