/// Jegyzetek — amit vissza akarok nézni, egy listában.
///
/// A jegyzetelés eddig egyirányú volt: a meccs közben meg lehetett
/// jelölni egy pillanatot, de utána csak ANNAK a meccsnek a
/// lejátszójában lehetett megtalálni. Az edző fejében viszont a
/// jegyzetek egyetlen listát alkotnak — "amit vissza akarok nézni" —,
/// és a hét közbeni munka ebből indul, nem meccsenként.
///
/// Ez a képernyő az összes jegyzetet mutatja meccs-környezettel és
/// játékidővel; egy sorra koppintva a meccs-elemző A MEGJELÖLT
/// pillanatnál nyílik meg. Kereshető, mert húsz meccs jegyzetei közt
/// már a szöveg a fogódzó, nem a dátum.
library;

import "package:flutter/material.dart";

import "../services/api_client.dart";
import "../theme/app_theme.dart";
import "error_text.dart";
import "match_screen.dart";
import "shell/app_shell.dart";
import "waiting.dart";

class NotesScreen extends StatefulWidget {
  const NotesScreen({super.key});

  @override
  State<NotesScreen> createState() => _NotesScreenState();
}

class _NotesScreenState extends State<NotesScreen> {
  final ApiClient _api = ApiClient();
  final TextEditingController _searchCtrl = TextEditingController();

  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _notes = [];
  String _query = "";
  // Épp törlés alatt álló jegyzet azonosítója — kétszer ne induljon.
  String? _deleting;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final n = await _api.fetchLibraryNotes();
      if (!mounted) return;
      setState(() {
        _notes = n;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = "A jegyzetek nem érhetők el: ${humanError(e)}";
        _loading = false;
      });
    }
  }

  List<Map<String, dynamic>> get _shown {
    if (_query.trim().isEmpty) return _notes;
    final q = _query.trim().toLowerCase();
    return [
      for (final n in _notes)
        if ("${n["text"]} ${n["home_team"]} ${n["away_team"]}"
            .toLowerCase()
            .contains(q))
          n
    ];
  }

  /// Jegyzet törlése — a lista az edző TEENDŐ-listája, tehát a kipipált
  /// tételnek le kell tudnia kerülni róla. Megerősítés nélkül nem
  /// törlünk: a jegyzet gépelt szöveg, nem újratermelhető adat.
  Future<void> _delete(Map<String, dynamic> n) async {
    final id = n["id"] as String?;
    final matchId = n["match_id"] as String?;
    if (id == null || matchId == null || _deleting != null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text("Jegyzet törlése"),
        content: SizedBox(
          width: 360,
          child: Text("„${n["text"]}”\n\nA törlés nem vonható vissza.",
              style: AppText.label.copyWith(fontSize: 12.5)),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text("Mégse")),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: AppColors.away,
                foregroundColor: AppColors.onAccent),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text("Törlés"),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _deleting = id);
    try {
      await _api.deleteNote(matchId, id);
      if (!mounted) return;
      setState(() {
        _notes = [for (final e in _notes) if (e["id"] != id) e];
        _deleting = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _deleting = null);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text("A törlés nem sikerült: ${humanError(e)}")));
    }
  }

  /// Játékidő óra-alakban (mm:ss) — a képkocka-index az edzőnek semmit
  /// nem mond, a perc igen.
  String _ora(num seconds) {
    final s = seconds.round();
    return "${(s ~/ 60).toString().padLeft(2, "0")}:"
        "${(s % 60).toString().padLeft(2, "0")}";
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.notes,
      crumbPath: "CSAPAT · JEGYZETEK",
      child: _loading
          ? const WaitingView("Jegyzetek összegyűjtése…",
              icon: Icons.sticky_note_2_outlined)
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Jegyzetek", style: AppText.title),
              const SizedBox(height: 4),
              Text(
                  "amit a meccsek közben megjelöltél — egy listában, "
                  "meccsektől függetlenül; koppints a visszanézéshez",
                  style: AppText.subtitle),
              const SizedBox(height: AppSpacing.lg),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Text(_error!,
                      style: AppText.label.copyWith(color: AppColors.away)),
                ),
              if (_notes.isEmpty)
                Text(
                    "Még nincs egyetlen jegyzet sem. A meccs-elemzőben "
                    "bármelyik pillanathoz írhatsz egyet — az ide is "
                    "bekerül, és a jegyzetelt pillanatokból klip is "
                    "vágható a Klipek menüben.",
                    style: AppText.label)
              else ...[
                _search(),
                const SizedBox(height: AppSpacing.md),
                Expanded(child: _list()),
              ],
            ]),
    );
  }

  Widget _search() {
    return SizedBox(
      width: 420,
      child: TextField(
        controller: _searchCtrl,
        style: AppText.value.copyWith(fontSize: 13),
        decoration: InputDecoration(
          isDense: true,
          hintText: "keresés a jegyzetek közt (szöveg vagy csapatnév)",
          hintStyle: AppText.label.copyWith(fontSize: 12.5),
          prefixIcon: const Icon(Icons.search, size: 18),
          border: const OutlineInputBorder(),
        ),
        onChanged: (v) => setState(() => _query = v),
      ),
    );
  }

  Widget _list() {
    final rows = _shown;
    if (rows.isEmpty) {
      return Text("Erre a keresésre nincs jegyzet.", style: AppText.label);
    }
    return ListView.builder(
      itemCount: rows.length,
      itemBuilder: (_, i) => _row(rows[i]),
    );
  }

  Widget _row(Map<String, dynamic> n) {
    final home = (n["home_team"] as String?) ?? "Hazai";
    final away = (n["away_team"] as String?) ?? "Vendég";
    final date = (n["date"] as String?) ?? "";
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: InkWell(
        onTap: () {
          Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => MatchScreen(
              matchId: n["match_id"] as String,
              initialFrame: (n["frame"] as num?)?.toInt() ?? 0,
            ),
          ));
        },
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: AppTheme.card(),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
              decoration: BoxDecoration(
                color: AppColors.surfaceAlt,
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: AppColors.borderStrong),
              ),
              child: Text(_ora((n["t_s"] as num?) ?? 0),
                  style: AppText.value.copyWith(fontSize: 12.5)),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text("${n["text"]}",
                        style: AppText.label.copyWith(
                            fontSize: 13, color: AppColors.textPrimary)),
                    const SizedBox(height: 3),
                    Text(
                        "$home – $away${date.isEmpty ? "" : " · $date"}",
                        style: AppText.label.copyWith(fontSize: 11)),
                  ]),
            ),
            const Icon(Icons.play_circle_outline,
                size: 18, color: AppColors.accent),
            IconButton(
              tooltip: "Jegyzet törlése",
              iconSize: 15,
              visualDensity: VisualDensity.compact,
              constraints: const BoxConstraints(),
              padding: const EdgeInsets.only(left: 8),
              icon: const Icon(Icons.delete_outline,
                  color: AppColors.textFaint),
              onPressed: _deleting != null ? null : () => _delete(n),
            ),
          ]),
        ),
      ),
    );
  }
}
