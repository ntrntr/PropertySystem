# -*- coding: utf-8 -*-
import weakref

PUSHABLE, NONPUSHABLE = 1, 2


class NodeFactory(object):

    def __init__(self, propDef):
        super(NodeFactory, self).__init__(propDef)
        self.propDef = weakref.proxy(propDef)


PUSHABLE, NONPUSHABLE = 1, 2
CLEAN, DIRTY, COND_DIRTY = 0, 1, 2


class Functor(object):
    def __init__(self, prop_def, name, update_mode=NONPUSHABLE):
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

    def __call__(self, def_var_name, depends, eval_functor, force_eval=False, update_mode=NONPUSHABLE, var_names=None):
        pass


class ExternFactory(NodeFactory):
    """
    外部变量
    """

    def __call__(self, def_var_name, var_names=None):
        if var_names is None:
            var_names = [def_var_name]
        self.prop_def.addProperty(ExtFunctor(self.prop_def, def_var_name), var_names=var_names)


class PropertyDefinition(NodeFactory):

    def __init__(self, propDef):
        super(PropertyDefinition, self).__init__(propDef)
        self.VAR = VarFactory(self)
        self.EXTERN = None


class PlayerPropDef(PropertyDefinition):
    pass
