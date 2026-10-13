"""
Town grid fixes from the Qwen3 8B town check (docs/PLAYTEST_ISSUES.md #56, #57, #58, #60).

The rule for all four (CLAUDE.md): the model keeps writing the town as it
likes; the engine matches what it wrote to the grid's real plots instead of
minting duplicates, and agrees with the prose when the prose goes indoors.
No model is called (writer-off fixtures from test_town_movement).
"""
from __future__ import annotations

import difflib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_town_movement import (  # noqa: E402
    _apply, _city, _fresh, _plan, _play, _pos, _scalar, connect, get_map, tg, tm, venues, world,
)


def _here():
    with connect() as conn:
        chart = get_map(None, conn=conn)
        pos = tm.get_position(conn)
        town = tg.stored_cell(conn, chart, pos["cx"], pos["cy"])
    return chart, pos, town


def _named_shop(town, *, kind: str = ""):
    for p in town["plots"]:
        if p.get("k") in ("shop", "service") and p.get("vk") and p.get("name") and p.get("f"):
            if not kind or p["vk"] == kind:
                return p
    return None


def _variant(name: str) -> str:
    """A near miss the way the 8B writes one ("Lucky Ox Outfitters" -> "Lucky Oxford Outfitters")."""
    words = name.split()
    i = next((k for k, w in enumerate(words) if w.isalpha() and w.lower() != "the"), 0)
    words[i] = words[i] + "ford"
    return " ".join(words)


class AdoptTheOpeningsRow(unittest.TestCase):
    """#56: the opening's 'Thirsty Wren Seamstress' (no plot) is the plot of that name, not a clash."""

    def setUp(self):
        self.chart = _fresh()
        self.city, _ = _city(self.chart)
        _apply(_plan("I look around."))

    def test_an_unplotted_row_of_the_plot_in_this_town_is_adopted(self):
        chart, pos, town = _here()
        shop = _named_shop(town)
        with connect() as conn:
            settle = tm.settlement_row(conn, self.city)
            conn.execute(
                "INSERT INTO locations (code, name, summary, parent_id, kind) VALUES ('L77', ?, 'from the opening', ?, ?)",
                (shop["name"], settle, shop["vk"]),
            )
            opening = conn.execute("SELECT id FROM locations WHERE code = 'L77'").fetchone()[0]
            got = tm.realize_plot(conn, chart, shop["id"])
            row = dict(conn.execute("SELECT * FROM locations WHERE id = ?", (got,)).fetchone())
            same = conn.execute("SELECT COUNT(*) FROM locations WHERE name LIKE ?", (shop["name"] + "%",)).fetchone()[0]
        self.assertEqual(got, opening, "the opening's row is the plot's row")
        self.assertEqual(row["plot_id"], shop["id"])
        self.assertEqual(row["city_id"], self.city["id"])
        self.assertEqual(row["name"], shop["name"])
        self.assertEqual(same, 1, "no 'on <street>' twin")

    def test_an_unrelated_row_elsewhere_is_still_a_clash(self):
        chart, pos, town = _here()
        shop = _named_shop(town)
        with connect() as conn:
            conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L88', ?, 'elsewhere')", (shop["name"],))
            other = conn.execute("SELECT id FROM locations WHERE code = 'L88'").fetchone()[0]
            got = tm.realize_plot(conn, chart, shop["id"])
        self.assertNotEqual(got, other)

    def test_entering_it_by_name_uses_the_adopted_row_and_rewind_restores_it(self):
        chart, pos, town = _here()
        shop = _named_shop(town)
        with connect() as conn:
            settle = tm.settlement_row(conn, self.city)
            conn.execute(
                "INSERT INTO locations (code, name, summary, parent_id, kind) VALUES ('L77', ?, '', ?, ?)",
                (shop["name"], settle, shop["vk"]),
            )
        with mock.patch.object(venues, "is_open", return_value=True):
            out = _play(f"I go into {shop['name']}.", f"You step into {shop['name']}.")
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations WHERE name LIKE ?", shop["name"] + "%"), 1)
        self.assertEqual(_scalar("SELECT code FROM locations WHERE plot_id = ?", shop["id"]), "L77")
        self.assertEqual(out["state"]["movement"]["rule"], "town_enter")
        world.rewind_last_turn()
        self.assertEqual(_scalar("SELECT COALESCE(plot_id, '') FROM locations WHERE code = 'L77'"), "",
                         "rewind un-adopts the opening's row")


class NearNamesFindThePlot(unittest.TestCase):
    """#57: 'Lucky Oxford Outfitters' is 'Lucky Ox Outfitters'; a LOC_NEW naming a plot mints no row."""

    def setUp(self):
        self.chart = _fresh()
        _play("I look around.", "You look about the lane.")

    def test_a_move_to_a_near_name_walks_to_the_real_plot(self):
        chart, pos, town = _here()
        shop = _named_shop(town)
        variant = _variant(shop["name"])
        self.assertGreaterEqual(difflib.SequenceMatcher(None, variant.lower(), shop["name"].lower()).ratio(), 0.8)
        with mock.patch.object(venues, "is_open", return_value=True):
            out = _play(f"I go into {variant}.", f"You walk over and step into {variant}.",
                        player={"move_to_location": variant})
        movement = out["state"]["movement"]
        self.assertEqual(movement.get("destination"), shop["name"], movement)
        self.assertIsNone(_scalar("SELECT id FROM locations WHERE name = ?", variant))
        narration = out.get("narration") or (out.get("turn") or {}).get("narration") or ""
        self.assertNotIn(variant, narration)

    def test_a_new_place_naming_a_plot_mints_no_row(self):
        chart, pos, town = _here()
        shop = _named_shop(town)
        variant = _variant(shop["name"])
        rows = _scalar("SELECT COUNT(*) FROM locations")
        out = _play("I look down the street.", f"Down the street stands {variant}, its shutters open.",
                    locations=[{"name": variant, "summary": "A shop down the street."}])
        self.assertIsNone(_scalar("SELECT id FROM locations WHERE name = ?", variant))
        self.assertIsNone(_scalar("SELECT id FROM locations WHERE name = ? AND COALESCE(plot_id, '') = ''", shop["name"]))
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows)
        narration = out.get("narration") or (out.get("turn") or {}).get("narration") or ""
        self.assertIn(shop["name"], narration, "the prose keeps the shop, under its real name")

    def test_a_gate_the_town_has_is_not_a_new_place(self):
        with connect() as conn:
            chart = get_map(None, conn=conn)
            pos = tm.get_position(conn)
            city = tm.city_by_id(chart, pos["city_id"])
            gates = [p for items in tg.city_ports(chart, city).values() for p in items if p.get("gate")]
        if not gates:
            self.skipTest("a gateless town")
        name = f"{str(gates[0]['gate']).title()} Gate"
        rows = _scalar("SELECT COUNT(*) FROM locations")
        _play("I look toward the wall.", f"Beyond the roofs you can make out the {name}.",
              locations=[{"name": name, "summary": "The town gate."}])
        self.assertIsNone(_scalar("SELECT id FROM locations WHERE name = ?", name))
        self.assertEqual(_scalar("SELECT COUNT(*) FROM locations"), rows)

    def test_the_general_store_is_a_store_not_the_nearest_door(self):
        chart, pos, town = _here()
        side = town["side"]
        stores = [p for p in town["plots"] if p.get("vk") == "general_store" and p.get("f")]
        others = [p for p in town["plots"] if p.get("k") in ("shop", "service") and p.get("vk") not in ("general_store", None)
                  and p.get("f")]
        if not stores or not others:
            self.skipTest("no general store beside another shop")
        # Stand at a door that is not a store, with a store within the near cap.
        found = None
        for store in stores:
            si = store["f"][1] * side + store["f"][0]
            near = tm._road_dist(town, si, limit=1)
            for i in near:
                plot = tm._frontage_plot(town, i)
                if plot is not None and plot.get("k") in ("shop", "service") and plot.get("vk") != "general_store":
                    found = (i, store)
                    break
            if found:
                break
        if not found:
            self.skipTest("no store next to another door")
        i, store = found
        with connect() as conn:
            city = tg._locate(chart, pos["cx"], pos["cy"])[0]
            here_pos = tm._make_position(chart, city, pos["cx"], pos["cy"], town, i)
            view = tm._CityView(conn, chart, city, here_pos, tm._CellSource(conn, chart, generate=False))
            hit = tm._shown_entry_plot(view, town, i, {"kind": "general_store", "noun": "store", "name": ""})
        self.assertIsNotNone(hit)
        self.assertEqual(hit[2].get("vk"), "general_store")


class ProseGoesInAtTheDoor(unittest.TestCase):
    """#58: 'I walk over to the seamstress' ends at the door; prose that goes in takes the player in."""

    def setUp(self):
        self.chart = _fresh()
        _play("I look around.", "You look about the lane.")

    def test_the_contract_says_at_the_door(self):
        tt = _plan("I walk over to the bakery.")
        self.assertEqual(tt["plan"]["kind"], "walk")
        self.assertIn("door", tt["contract"]["arrived"]["where"])

    def test_prose_that_goes_inside_enters_the_shop_the_walk_reached(self):
        with mock.patch.object(venues, "is_open", return_value=True):
            out = _play("I walk over to the bakery.",
                        "You cross the lane to the bakery. You push the door open and step inside, where the ovens breathe.")
        movement = out["state"]["movement"]
        with connect() as conn:
            pos = tm.get_position(conn)
            here = conn.execute(
                "SELECT l.plot_id FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
            ).fetchone()
        self.assertTrue(pos["inside"], movement)
        self.assertEqual(here["plot_id"], pos["inside"])

    def test_prose_that_stays_outside_leaves_the_player_at_the_door(self):
        with mock.patch.object(venues, "is_open", return_value=True):
            _play("I walk over to the bakery.", "You cross the lane and stop outside the bakery, smelling the bread.")
        self.assertEqual(_pos()["inside"], "")

    def test_a_closed_shop_is_not_entered_even_when_the_prose_goes_in(self):
        with mock.patch.object(venues, "is_open", return_value=False):
            _play("I walk over to the bakery.", "You cross the lane to the bakery and step inside.")
        self.assertEqual(_pos()["inside"], "")


class StreetSpreadAndWorkplaces(unittest.TestCase):
    """#60: one street does not repeat a trade door after door; a stale workplace plan follows the role."""

    def setUp(self):
        self.chart = _fresh()
        self.city, _ = _city(self.chart)
        _apply(_plan("I look around."))

    def test_one_trade_is_not_repeated_close_along_one_street(self):
        with connect() as conn:
            chart = get_map(None, conn=conn)
            cells = tm._generated_cells(conn, chart, self.city["id"])
            towns = [tg.stored_cell(conn, chart, *xy) for xy in cells]
        crowded = []
        for town in towns:
            gap = tg.same_kind_gap_tiles(int(town["side"]))
            by: dict[tuple[int, str], list[list[int]]] = {}
            for p in town["plots"]:
                if p.get("vk") and p.get("f") and p.get("seg") is not None and "stall" not in (p.get("fl") or []):
                    by.setdefault((int(p["seg"]), p["vk"]), []).append(p["f"])
            for (seg, vk), fronts in by.items():
                for a in range(len(fronts)):
                    for b in range(a + 1, len(fronts)):
                        d = abs(fronts[a][0] - fronts[b][0]) + abs(fronts[a][1] - fronts[b][1])
                        if d < gap:
                            crowded.append((seg, vk, d))
        self.assertEqual(crowded, [])

    def test_a_workplace_plan_for_an_old_trade_is_replaced(self):
        with connect() as conn:
            settle = tm.settlement_row(conn, self.city)
            conn.execute("UPDATE player SET current_location_id = ? WHERE id = 1", (settle,))
            cur = conn.execute(
                "INSERT INTO npcs (code, location_id, name, role, summary) VALUES (?, ?, 'Bennet', 'stable hand', '')",
                (world._next_alpha_code(conn), settle),
            )
            npc = int(cur.lastrowid)
            world.plan_npc_workplace(conn, npc)
            before = world.npc_workplace_plan(conn, npc)
            conn.execute("UPDATE npcs SET role = 'tailor' WHERE id = ?", (npc,))
            world.plan_npc_workplace(conn, npc)
            after = world.npc_workplace_plan(conn, npc)
        if before.get("kind") == "tailor":
            self.skipTest("the stable hand already had a tailor plan")
        self.assertEqual(after.get("kind"), "tailor", after)

    def test_met_inside_a_shop_of_their_trade_they_work_there(self):
        chart, pos, town = _here()
        shop = _named_shop(town, kind="tailor") or _named_shop(town)
        role = {"tailor": "tailor", "bakery": "baker", "general_store": "shopkeeper"}.get(shop["vk"], "")
        with connect() as conn:
            if not role or shop["vk"] not in venues.workplace_kinds_for_role(role, world._world_era(conn)):
                self.skipTest("no role for this trade")
            venue = tm.realize_plot(conn, chart, shop["id"])
            cur = conn.execute(
                "INSERT INTO npcs (code, location_id, name, role, summary, workplace_plan, workplace_plot) "
                "VALUES (?, ?, 'Bennet', ?, '', ?, 'C0.0.0.1')",
                (world._next_alpha_code(conn), venue, role,
                 json.dumps({"kind": "stable", "name": "Broken Ferret Stable", "plot_id": "C0.0.0.1", "city_id": self.city["id"]})),
            )
            npc = int(cur.lastrowid)
            got = world.plan_npc_workplace(conn, npc)
        self.assertEqual(got, venue)


if __name__ == "__main__":
    unittest.main()
