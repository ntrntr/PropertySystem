# -*- coding: utf-8 -*-
import weakref
import random

PUSHABLE, NONPUSHABLE = 1, 2

CLEAN, DIRTY, COND_DIRTY = 0, 1, 2

class LocalPropertySlot(object):
	# @dirty
	#	0: clean
	#	1: dirty
	#	2: conditional dirty (default)
	#
	#	So after migration, every node by default is marked as conditional dirty

	def __init__(self):
		self.dirty = COND_DIRTY # conditional dirty
		self.var_value = None

	def __repr__(self):
		return '<%d, %s>' % (self.dirty, self.var_value)

class NodeFactory(object):

    def __init__(self, propDef):
        self.prop_def = weakref.proxy(propDef)

class Functor(object):
    def __init__(self, prop_def, name,
                 update_mode=NONPUSHABLE):
        self.name = name
        # 依赖变量
        self.depends = []
        # 影响变量
        self.deriveds = []
        self.force_eval = False
        self.update_mode = update_mode

    def set_local_prop_slot_idx(self, prop_def, idx):
        self.local_prop_slot_idx = idx

    def getPropertyStateSlot(self, prop_holder):
        return prop_holder._local_property_state[self.local_prop_slot_idx]

    def evaluate(self, prop_holder):
        raise NotImplemented

    def _evaluate(self, prop_holder):
        raise NotImplemented

    def _forceEvaluate(self, prop_holder, do_decend, do_update, old_prop_value=None):
        raise NotImplemented

    def update(self, prop_holder, v):
        raise NotImplemented

    def depend(self, prop_def, f):
        self.depends.append(f)
        p = prop_def._getProperty(f)
        assert p, f
        p._derive(self.name)
        self.force_eval = self.force_eval or p.force_eval

    def drop(self, prop_def):
        for dn in self.depends:
            d = prop_def._getProperty(dn)
            d.deriveds.remove(self.name)

        prop_def.removeProperty(self.name)

    def markInvalid(self, prop_holder):
        self.prop_holder = prop_holder
        prop_holder._local_property_state[self.local_prop_slot_idx].dirty = COND_DIRTY

    def _derive(self, f):
        self.deriveds.append(f)

    def _invalidateChildren(self, prop_holder):
        prop_def = prop_holder.property_def

        for p in [prop_def._getProperty(x) for x in self.deriveds]:
            # print "_invalidateChildren to ", p.name
            slot = prop_holder._local_property_state[p.local_prop_slot_idx]
            if slot.dirty == CLEAN:
                slot.dirty = DIRTY
                p._invalidateChildren(prop_holder)

    def _pushNewValueToChildren(self, prop_holder):
        prop_def = prop_holder.property_def
        deriveds = prop_def.update_var_seq.get(self.name)
        if deriveds:
            for dn in deriveds:
                d = prop_def._getProperty(dn)
                slot = prop_holder._local_property_state[d.local_prop_slot_idx]
                d._forceEvaluate(prop_holder, do_decend=(slot.dirty == COND_DIRTY), do_update=True)
                if slot.dirty != CLEAN:
                    return

    def _onUpdated(self, prop_holder, old_value, new_value):
        if self.update_mode == PUSHABLE and old_value != new_value:
            prop_def = prop_holder.property_def
            for pn in prop_def.alias_map[self.name]:
                prop_def._onPropertyValueUpdated(prop_holder, pn, old_value, new_value)


class VarFunctor(Functor):
    def __init__(self, prop_def,
                 name,
                 eval_cls, eval_functor,
                 force_eval, update_mode):
        super(VarFunctor, self).__init__(prop_def, name, update_mode=update_mode)

        self.eval_cls = eval_cls
        self.eval_functor = eval_functor
        self.force_eval = self.force_eval or force_eval

    def evaluate(self, prop_holder):
        self._evaluate(prop_holder)
        slot = prop_holder._local_property_state[self.local_prop_slot_idx]
        assert slot.dirty == CLEAN, "VarFunctor::evaluate must be called when it's already ready.(%s)" % self.name
        return slot.var_value

    def _evaluate(self, prop_holder):
        slot = prop_holder._local_property_state[self.local_prop_slot_idx]
        if self.force_eval or slot.dirty != CLEAN:
            self._forceEvaluate(prop_holder, do_decend=True, do_update=False)
            if slot.dirty == CLEAN:
                return slot.var_value
            else:
                return None
        else:
            return slot.var_value

    def _forceEvaluate(self, prop_holder, do_decend, do_update, old_prop_value=None):
        prop_def = prop_holder.property_def
        args = [None for i in range(len(self.depends))]
        slot = prop_holder._local_property_state[self.local_prop_slot_idx]
        for i, d in enumerate(self.depends):
            p = prop_def._getProperty(d)
            pslot = prop_holder._local_property_state[p.local_prop_slot_idx]

            if pslot.dirty and not do_decend:
                print "VarFunctor %s Eval Fail at sub-property %s" % (self.name, d)
                slot.dirty = DIRTY
                return

            v = p._evaluate(prop_holder)

            if pslot.dirty == CLEAN:
                args[i] = v
            else:
                print "VarFunctor %s Eval Fail at sub-property %s" % (self.name, d)
                slot.dirty = DIRTY
                return

        var_value = self.callEvalFunctor(prop_holder, *args)
        old_value, slot.var_value = slot.var_value, var_value
        slot.dirty = CLEAN

        if do_update:
            if old_prop_value is not None:
                old_value = old_prop_value
            self._onUpdated(prop_holder, old_value, slot.var_value)

    def callEvalFunctor(self, prop_holder, *args):
        if type(self.eval_functor) is str:
            return getattr(self.eval_cls, self.eval_functor)(self, prop_holder, *args)
        else:
            return self.eval_functor(self, prop_holder, *args)


class ExtFunctor(Functor):
    def __init__(self, prop_def, name):
        super(ExtFunctor, self).__init__(prop_def, name, update_mode=NONPUSHABLE)
        self.force_eval = False

    def set_local_prop_slot_idx(self, prop_def, idx):
        super(ExtFunctor, self).set_local_prop_slot_idx(prop_def, idx)
        prop_def.setAlwaysValid(self.local_prop_slot_idx)

    def update(self, prop_holder, v):
        self._onPendingUpdate(prop_holder)
        old_value = getattr(prop_holder, self.name)
        setattr(prop_holder, self.name, v)
        prop_holder._local_property_state[self.local_prop_slot_idx].dirty = CLEAN
        self._invalidateChildren(prop_holder)
        self._pushNewValueToChildren(prop_holder)
        self._onUpdated(prop_holder, old_value, v)

    def evaluate(self, prop_holder):
        return self._evaluate(prop_holder)

    def _evaluate(self, prop_holder, do_assert=False):
        try:
            val = getattr(prop_holder, self.name)
        except AttributeError:
            prop_holder._local_property_state[self.local_prop_slot_idx].dirty = DIRTY
            assert False, "ExtFunctor: property (%s) is not ready" % self.name
            return None
        else:
            prop_holder._local_property_state[self.local_prop_slot_idx].dirty = CLEAN
            return val

    def _forceEvaluate(self, prop_holder, do_decend, do_update, old_prop_value=None):
        # only called from recovery
        try:
            val = getattr(prop_holder, self.name)
        except AttributeError:
            prop_holder._local_property_state[self.local_prop_slot_idx].dirty = DIRTY
        else:
            prop_holder._local_property_state[self.local_prop_slot_idx].dirty = CLEAN
            assert not do_update, self.name

    def _onPendingUpdate(self, prop_holder):
        prop_holder.property_def._onExternPropertyValuePendingUpdate(prop_holder, self.name,
                                                                     getattr(prop_holder, self.name))

    def _onUpdated(self, prop_holder, old_value, new_value):
        if old_value != new_value:
            prop_holder.property_def._onPropertyValueUpdated(prop_holder, self.name, old_value, new_value)

class VarFactory(NodeFactory):
    """
    外部变量
    """

    def __init__(self, propDef):
        super(VarFactory, self).__init__(propDef)
        self.params = {}

    def setNodeParam(self, param_name, param_value):
        self.params[param_name] = param_value

    def __call__(self, def_var_name, depends, eval_functor, force_eval=False, update_mode=NONPUSHABLE, var_names=None, init_eval = False):
        var = VarFunctor(self.prop_def,
                         def_var_name,
                         self.prop_def, eval_functor,
                         force_eval, update_mode)

        if self.params:
            for pn, p in self.params.iteritems():
                setattr(var, pn, p)
            self.params = {}

        def setupDepends():
            for d in depends:
                var.depend(self.prop_def, d)

        if var_names is None:
            var_names = [def_var_name]
        self.prop_def.addProperty(var, late_setup=setupDepends, var_names=var_names, init_eval=init_eval)


class ExternFactory(NodeFactory):
    """
    外部变量
    """

    def __call__(self, def_var_name, var_names=None):
        if var_names is None:
            var_names = [def_var_name]
        self.prop_def.addProperty(ExtFunctor(self.prop_def, def_var_name), var_names=var_names)


class PropertyDefinition(object):

    def __init__(self):
        self.property_store = {}
        self.alias_map = {}
        self.init_eval = []
        self._local_property_state_num = 0
        self.always_true_nodes = []
        self.late_setup = []

        self.VAR = VarFactory(self)
        self.EXTERN = ExternFactory(self)

        # user definitions
        self.define()

        # internal definitions
        self._internalDefinitions()

        for late_setup_functor in self.late_setup:
            late_setup_functor()

        del self.late_setup

        self.calculateUpdateSequence()

    @property
    def local_property_state_num(self):
        return self._local_property_state_num

    def define(self):
        pass

    def PVrefresh(self, prop_holder):
        for p in self.property_store.itervalues():
            p.markInvalid(prop_holder)

    def hasProperty(self, prop):
        return prop in self.property_store

    def _getProperty(self, prop_name):
        assert prop_name in self.property_store, '%s has not %s' % (self, prop_name)
        return self.property_store.get(prop_name)

    def setAlwaysValid(self, slot_idx):
        self.always_true_nodes.append(slot_idx)

    def initEvals(self, prop_holder):
        for pn in self.init_eval:
            p = self._getProperty(pn)
            v = p.evaluate(prop_holder)

            slot = p.getPropertyStateSlot(prop_holder)
            if slot.dirty == CLEAN:
                p._onUpdated(prop_holder, None, v)

    def getNextAvailableSlotIdx(self):
        local_idx, self._local_property_state_num = self._local_property_state_num, self._local_property_state_num + 1
        return local_idx

    def addProperty(self, prop, late_setup=None, var_names=None, init_eval=False):
        if var_names is None:
            var_names = [prop.name]

        self.alias_map[prop.name] = var_names

        for vn in var_names:
            self.property_store[vn] = prop

        local_prop_slot_idx = self.getNextAvailableSlotIdx()
        prop.set_local_prop_slot_idx(self, local_prop_slot_idx)

        if late_setup:
            self.late_setup.append(late_setup)

        if init_eval:
            self.init_eval.append(prop.name)

    def removeProperty(self, pn):
        p = self._getProperty(pn)
        var_names = self.alias_map[p.name]
        for v in var_names:
            del self.property_store[v]

        del self.alias_map[p.name]

    def initPropertyHolder(self, prop_holder):
        self.initAlwaysTrueNodes(prop_holder)

    def initAlwaysTrueNodes(self, prop_holder):
        slots = prop_holder._local_property_state
        for pidx in self.always_true_nodes:
            slot = slots[pidx]
            slot.dirty = CLEAN

    def invalidateAllNodes(self, prop_holder):
        slots = prop_holder._local_property_state
        for s in slots:
            s.dirty = COND_DIRTY

        self.initAlwaysTrueNodes(prop_holder)

    def PV(self, prop_holder, prop_name, *default):
        if not default or self.hasProperty(prop_name):
            return self._getProperty(prop_name).evaluate(prop_holder)
        else:
            return default[0]

    def updatePV(self, prop_holder, prop_name, v):
        self._getProperty(prop_name).update(prop_holder, v)

    def _onPropertyValueUpdated(self, prop_holder, name, old_val, new_val):
        var_names = self.alias_map.get(name, [name])
        for vn in var_names:
            prop_holder.onPropertyValueUpdated(vn, old_val, new_val)

    def _internalDefinitions(self):
        self.EXTERN('prop_random')

    def regenRandomNum(self, prop_holder):
        self.updatePV(prop_holder, 'prop_random', random.random())

    def _onExternPropertyValuePendingUpdate(self, prop_holder, name, cur_val):
        if name == 'prop_random':
            return

        var_names = self.alias_map.get(name, [name])
        for vn in var_names:
            prop_holder.onExternPropertyValuePendingUpdate(vn, cur_val)

    @classmethod
    def is_extern_functor(cls, ftor):
        return isinstance(ftor, (ExtFunctor,))

    def getExternPropertyNames(self):
        nms = []
        for v in self.property_store.itervalues():
            if self.is_extern_functor(v) and v.name not in ('prop_random',):
                nms.append(v.name)

        return nms

    def calculateUpdateSequence(self):
        ext_names = self.getExternPropertyNames()
        self.update_var_seq = {}
        for en in ext_names:
            e = self._getProperty(en)
            inarc = {e.name: 0}
            tq = [e]
            visited = set([e.name])
            while tq:
                c = tq.pop()
                # print "c.name tt", c.name
                for dn in c.deriveds:
                    d = self._getProperty(dn)
                    # print "d.name", d.name, visited, d.update_mode, PUSHABLE
                    if d.update_mode == PUSHABLE:
                        inarc[d.name] = inarc.get(d.name, 0) + 1
                        # print "inarc add", d.name, visited
                        if d.name not in visited:
                            visited.add(d.name)
                            tq.append(d)

            seq = []
            tq = [e]
            while tq:
                c = tq.pop()
                seq.append(c.name)
                ins = inarc[c.name]
                assert ins == 0, c.name
                for dn in c.deriveds:
                    d = self._getProperty(dn)
                    if d.update_mode == PUSHABLE:
                        inarc[d.name] -= 1
                        if inarc[d.name] == 0:
                            tq.append(d)

            assert all((x == 0 for x in inarc.values())), inarc
            self.update_var_seq[e.name] = seq[1:]


class PlayerPropDef(PropertyDefinition):

    def do_roll(self, node, attd_ety, level, prop_random):
        print "level", level, attd_ety.param['attacker_level'], (level - attd_ety.param['attacker_level']) / level
        return prop_random < (level - attd_ety.param['attacker_level']) *1.0 / level

    def base_hurt(self, node, attd_ety, do_roll, strength, equip_strength):
        if do_roll:
            return strength * equip_strength * 1.5
        else:
            return strength * equip_strength

    def define(self):
        super(PlayerPropDef, self).define()
        self.EXTERN('level')
        self.EXTERN('strength')
        self.EXTERN('equip_strength')
        self.VAR('do_roll', ['level', 'prop_random'], 'do_roll')
        self.VAR('base_hurt', ['do_roll', 'strength', 'equip_strength'], 'base_hurt')

class iPropertySystem(object):
    def __init__(self):
        super(iPropertySystem, self).__init__()
        self._property_def = None

    @property
    def property_def(self):
        if not self._property_def:
            self._property_def = PlayerPropDef()
        return self._property_def

    def PV(self, prop_name, *default):
        return self.property_def.PV(self, prop_name, *default)

    def updatePV(self,  prop_name, v):
        self.property_def.updatePV(self, prop_name, v)

    def initProperty(self):
        lc = [LocalPropertySlot() for i in range(self.property_def.local_property_state_num)]
        self._local_property_state = lc
        self.property_def.initPropertyHolder(self)

    def regenRandomNum(self):
        self.property_def.regenRandomNum(self)

    def onPropertyValueUpdated(self, name, old_val, new_val):
        print "name:%s update from:%s to:%s" % (name, old_val, new_val)


class Avatar(iPropertySystem):

    def __init__(self):
        super(Avatar, self).__init__()

    def init(self):
        self.prop_random = 0
        self.level = 2
        self.strength = 1
        self.equip_strength = 1
        self.param = {}
        self.initProperty()

    def onExternPropertyValuePendingUpdate(self, name, cur_val):
        print "name:%s cur_val:%s" % (name, cur_val, )



if __name__ == '__main__':
    avatar = Avatar()
    avatar.init()
    print avatar.PV('prop_random')
    avatar.regenRandomNum()
    avatar.param = {"attacker_level":1}
    print "prop_radom:%s" % (avatar.PV('prop_random'), )
    print avatar.PV('level')
    print avatar.PV('do_roll')
    print avatar.PV('base_hurt')