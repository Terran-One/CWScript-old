from typing import List

from cwscript.lang.ast import *
from cwscript.lang.ast import _Ast
from cwscript.template import codegen_templates as t
from cwscript.util.context_env import Context, Env


class CGContext(Context):
    pass


class CGEnv(Env):
    pass


class ContractCodegen(AstVisitor):
    def __init__(self, contract_defn: ContractDefn):
        self.defn = contract_defn


class ICodegen:
    """Interface to allow for code generation.
    Note the pattern:

        1. `generate_code()` is the public interface and is already implemented
            for you. Modify `_gen_code()` to define what code to generate.
        2. `_gen_code()` and `_verify` are private, don't call them directly
            from within a foreign class. Use `generate_code()` which calls
            both `_verify()` and `_gen_code()`.
        3. You can subclass `ICodegen.VerifyError`.
    """

    class VerificationError(Exception):
        """Error during verification"""

    class GenerationError(Exception):
        """Error during code-generation"""

    def _gen_code(self, env: CGEnv) -> str:
        raise NotImplementedError(f"_gen_code() not implemented for {self.__class__}")

    def _verify(self, env: CGEnv):
        """Perform checks for validity, raise an Exception."""
        pass

    def generate_code(self, env: CGEnv) -> str:
        """Generate code for this node."""
        env.push(self)
        self._verify(env)
        code = self._gen_code(env)
        env.pop()
        assert code is not None
        return code


"""Symbolic execution"""
from dataclasses import dataclass
from os import sendfile
from typing import List

from cwscript.lang.ast import *
from cwscript.lang.ast import _Ast
from cwscript.template import codegen_templates as t
from cwscript.util.context_env import Context, Env


class IR:
    pass


@dataclass
class IRMapRef:
    base_key: str
    keys: List[str]


@dataclass
class IRItemRef:
    key: str


def compat(type1: str, type2: str):
    return True


class SymExecVisitor:
    def __init__(self, env=None):
        self.env = env or Env()
        self.code = []

    def push(self, item):
        self.code.append(item)

    def pop(self, item):
        self.code.pop(item)

    def visit(self, ast: _Ast):
        if ast is None:
            return None
        if iis(ast, list, tuple):
            return [self.visit(x) for x in ast]
        if isinstance(ast, ExecDefn):
            name = str(ast.name)
            args = [(str(arg.name), arg.type) for arg in ast.args]
            body = self.visit(ast.body)
            res = t["exec-fn"].render(name=name, args=args, body=body)
            print(res)
            return res
        if isinstance(ast, IfExpr):
            ctx = dict(
                if_clause=self.visit(ast.if_clause),
                else_if_clauses=self.visit(ast.else_if_clauses),
                else_body=self.visit(ast.else_body),
            )
            return t["if-expr"].render(**ctx)
        if isinstance(ast, AssignStmt):
            # there are several types of assignments
            # 1 - state-item-assign
            # state count: i32
            # $state.count = 31
            # 2 - state-map-assign
            # state balances[user: Addr][token: Addr]: Uint128
            # $state.balances[terra1...][terra1...] = 1
            ctx = dict(
                lhs=self.visit(ast.lhs),
                rhs=self.visit(ast.rhs),
            )
            ctx["lhs_is_ident"] = isinstance(ast.lhs, Ident)
            ctx["rhs_is_item"] = isinstance(ctx["rhs"], IRItemRef)
            if isinstance(ctx["lhs"], IRItemRef):
                # check that types match
                return t["set-state-item"].render(**ctx)
            elif isinstance(ctx["lhs"], IRMapRef):
                return t["set-state-map"].render(**ctx)
            else:
                return t["set-variable"].render(**ctx)
        if isinstance(ast, TableLookupExpr):
            item = self.visit(ast.item)
            key = self.visit(ast.key)
            if iis(item, IRItemRef):
                return IRMapRef(item.key, [key])
            return ("lookup", self.visit(ast.item), self.visit(ast.key))
        if isinstance(ast, MemberAccessExpr):
            item = self.visit(ast.item)
            member = self.visit(ast.member)
            if item == "$state":
                return IRItemRef(member)
            if item == "$msg":
                return f"info.{member}"
            return f"{self.visit(ast.item)}.{self.visit(ast.member)}"
        if isinstance(ast, Ident):
            return str(ast)
        # if isinstance(ast, EmitStmt):
        #     return ('emit', self.visit(ast.expr))
        # if isinstance(ast, FnCallExpr):
        #     return ('fn-call', self.visit(ast.fn_name), self.visit(ast.args))
        return f"// Omitted: {str(ast)}"
