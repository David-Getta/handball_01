/// Meccs-képernyő — betölti a Tracking-et, és lejátssza a felülnézeti nézeten.
///
/// Adatforrás: ha a lokális backend elérhető, onnan kéri a meccset; különben a
/// beágyazott demó-adatra esik vissza (így backend nélkül is működik).
/// Vezérlés: lejátszás/szünet és egy idővonal-csúszka a frame-ek között.
library;

import "dart:async";
import "package:flutter/material.dart";

import "../models/tracking.dart";
import "../services/api_client.dart";
import "../sim/demo_data.dart";
import "court_painter.dart";

class MatchScreen extends StatefulWidget {
  /// A betöltendő meccs azonosítója a backendből (ha elérhető).
  final String matchId;

  const MatchScreen({super.key, this.matchId = "sim-0"});

  @override
  State<MatchScreen> createState() => _MatchScreenState();
}

class _MatchScreenState extends State<MatchScreen> {
  final ApiClient _api = ApiClient();

  Match? _match;
  int _frameIndex = 0;
  bool _playing = false;
  String _sourceLabel = "betöltés…";
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  /// Betöltés: előbb a lokális backend, ha nem megy, a beágyazott demó.
  Future<void> _load() async {
    Match match;
    String label;
    if (await _api.isHealthy()) {
      try {
        match = await _api.fetchMatch(widget.matchId);
        label = "backend (localhost): ${match.meta.matchId}";
      } catch (e) {
        match = buildDemoMatch();
        label = "demó (backend hiba: $e)";
      }
    } else {
      match = buildDemoMatch();
      label = "demó (nincs backend)";
    }
    setState(() {
      _match = match;
      _sourceLabel = label;
      _frameIndex = 0;
    });
  }

  void _togglePlay() {
    final match = _match;
    if (match == null) return;
    setState(() => _playing = !_playing);
    _timer?.cancel();
    if (_playing) {
      final fps = match.meta.fps > 0 ? match.meta.fps : 25.0;
      _timer = Timer.periodic(Duration(milliseconds: (1000 / fps).round()), (_) {
        setState(() {
          if (_frameIndex < match.frames.length - 1) {
            _frameIndex++;
          } else {
            _playing = false;
            _timer?.cancel();
          }
        });
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final match = _match;
    return Scaffold(
      appBar: AppBar(
        title: const Text("Kézilabda — felülnézeti nézet"),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh), tooltip: "Újratöltés"),
        ],
      ),
      body: match == null
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                _legend(match),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: CustomPaint(
                      painter: CourtPainter(frame: match.frames[_frameIndex]),
                      size: Size.infinite,
                    ),
                  ),
                ),
                _controls(match),
              ],
            ),
    );
  }

  Widget _legend(Match match) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Row(
        children: [
          _dot(const Color(0xFF1E66F5)),
          Text("  ${match.meta.homeTeam}    "),
          _dot(const Color(0xFFE5484D)),
          Text("  ${match.meta.awayTeam}    "),
          const Text("○ becsült (halvány)   "),
          const Spacer(),
          Text("forrás: $_sourceLabel", style: const TextStyle(fontSize: 12, color: Colors.grey)),
        ],
      ),
    );
  }

  Widget _dot(Color c) => Container(width: 14, height: 14, decoration: BoxDecoration(color: c, shape: BoxShape.circle));

  Widget _controls(Match match) {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          IconButton(
            iconSize: 32,
            onPressed: _togglePlay,
            icon: Icon(_playing ? Icons.pause_circle : Icons.play_circle),
          ),
          Expanded(
            child: Slider(
              value: _frameIndex.toDouble(),
              min: 0,
              max: (match.frames.length - 1).toDouble(),
              onChanged: (v) => setState(() => _frameIndex = v.round()),
            ),
          ),
          // Frame-index és idő (másodperc) kijelzése.
          Text("${_frameIndex + 1}/${match.frames.length}  "
              "(${(_frameIndex / (match.meta.fps > 0 ? match.meta.fps : 25.0)).toStringAsFixed(1)} s)"),
        ],
      ),
    );
  }
}
