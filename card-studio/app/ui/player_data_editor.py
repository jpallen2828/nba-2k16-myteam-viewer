"""Full NBA 2K16 player-data editor used by the card-authoring workflow."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCompleter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from app.player_data.schema import (
    ATTRIBUTE_GROUPS, GAMEPLAY_BADGES, NBA_FRANCHISES,
    FORCE_NON_STARTER_OPTIONS, HOT_ZONES, INJURY_OPTIONS, PERSONALITY_BADGES,
    OVERALL_ATTRIBUTE_FIELDS, PLAY_TYPE_OPTIONS, POSITIONS, SIGNATURE_GROUPS, TENDENCY_GROUPS, TIERS,
    normalize_player_data, pretty_name,
)
from app.player_data.overall_calculator import OverallCalculator, OverallEstimate
from app.player_data.preset_database import PlayerPresetDatabase


class PlayerDataEditor(QWidget):
    done_requested = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._controls: dict[str, QWidget] = {}
        self._preset_database = PlayerPresetDatabase()
        self._preset_combo: QComboBox | None = None
        self._overall_calculator = OverallCalculator.load_default()
        self._overall_live_display: QLabel | None = None
        self._source_identity = {"source_card_id": 0, "source_card_slug": "", "source_identity_ids": {}}
        root = QVBoxLayout(self)
        heading = QHBoxLayout()
        title = QLabel("Player Data")
        title.setObjectName("playerDataTitle")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        heading.addWidget(title)
        overall_display = QLabel("OVR --.--")
        overall_display.setObjectName("overallLiveDisplay")
        overall_display.setStyleSheet("font-size: 22px; font-weight: 700; color: #35d7ff;")
        self._overall_live_display = overall_display
        heading.addSpacing(12)
        heading.addWidget(overall_display)
        heading.addStretch(1)
        note = QLabel("Fields follow NBA 2K16's player editor and verified memory layout.")
        note.setStyleSheet("color: #9fb0c5;")
        heading.addWidget(note)
        done = QPushButton("Done")
        done.setObjectName("primaryButton")
        done.clicked.connect(lambda: self.done_requested.emit(self.player_data()))
        heading.addWidget(done)
        root.addLayout(heading)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._vitals_page(), "Vitals")
        self.tabs.addTab(self._ratings_page(ATTRIBUTE_GROUPS, "attributes", 25, 99, 75), "Attributes")
        self.tabs.addTab(self._ratings_page(TENDENCY_GROUPS, "tendencies", 0, 100, 50), "Tendencies")
        self.tabs.addTab(self._signatures_page(), "Signature Animations")
        self.tabs.addTab(self._badges_page(), "Badges")
        self.tabs.addTab(self._hot_zones_page(), "Hot Zones")
        root.addWidget(self.tabs, 1)
        self._connect_overall_calculator()
        self._update_overall_estimate()

    @staticmethod
    def _scroll(content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _register(self, key: str, widget: QWidget) -> QWidget:
        self._controls[key] = widget
        return widget

    def _line(self, key: str, maximum: int = 80) -> QLineEdit:
        field = QLineEdit()
        field.setMaxLength(maximum)
        return self._register(key, field)  # type: ignore[return-value]

    def _spin(self, key: str, minimum: int, maximum: int, value: int) -> QSpinBox:
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(value)
        return self._register(key, field)  # type: ignore[return-value]

    def _combo(self, key: str, values: tuple[str, ...] | list[str], allow_blank: bool = False) -> QComboBox:
        field = QComboBox()
        if allow_blank:
            field.addItem("None", "")
        for value in values:
            field.addItem(value, value)
        return self._register(key, field)  # type: ignore[return-value]

    def _searchable_player_combo(self) -> QComboBox:
        field = QComboBox()
        field.setEditable(True)
        field.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        field.setMaxVisibleItems(18)
        field.setPlaceholderText("Type a player name or choose an existing card…")
        field.activated.connect(self._apply_selected_preset)
        self._preset_combo = field
        return field

    def _taxonomy_combo(self, key: str) -> QComboBox:
        field = QComboBox()
        field.setMaxVisibleItems(24)
        return self._register(key, field)  # type: ignore[return-value]

    @staticmethod
    def _choice_label(label: str) -> str:
        return label.replace("_", " ").title().replace("Pnr", "P&R").replace("Nba", "NBA").replace("Iso", "ISO")

    @staticmethod
    def _dunk_choice_label(label: str) -> str:
        """Split the compact names preserved by the game table into English words."""
        words = (
            "UNDER", "BASKET", "STRAIGHT", "ATHLETIC", "SCRATCHERS", "SCRATCHER",
            "TOMAHAWKS", "WINDMILLS", "WINDMILL", "SWITCHEROOS", "HISTORIC",
            "DOUBLE", "CLUTCH", "BASELINE", "REGULAR", "QUICK", "DROPS", "DROP",
            "REVERSES", "REVERSE", "GRAZERS", "CRADLES", "LEANING", "SPRITE", "BLACKTOP",
            "FIST", "PUMP", "COCK", "BACK", "FRONT", "SIDE", "ARM", "UBER",
            "LEANS", "HANGS", "BASIC", "BIG", "MAN", "RIM", "PULLS", "ONE",
            "TWO", "FOOT", "HAND", "JORDAN", "DREXLER", "DUNKS", "NONE",
            "DEFAULT", "IN", "180", "360S",
        )
        compact = label.replace("_", "").upper()
        ordered = sorted(words, key=len, reverse=True)
        result: list[str] = []
        while compact:
            token = next((word for word in ordered if compact.startswith(word)), None)
            if token is None:
                return PlayerDataEditor._choice_label(label)
            result.append(token)
            compact = compact[len(token):]
        replacements = {"RIM": "Rim", "UBER": "Uber", "180": "180", "360S": "360s"}
        return " ".join(replacements.get(word, word.title()) for word in result)

    def _id_combo(self, key: str, values: tuple[tuple[int, str], ...], *, dunk_labels: bool = False) -> QComboBox:
        field = QComboBox()
        for value, label in values:
            display = self._dunk_choice_label(label) if dunk_labels else self._choice_label(label)
            field.addItem(f"{display} (ID {value})", value)
        return self._register(key, field)  # type: ignore[return-value]

    def _jersey_combo(self) -> QComboBox:
        field = QComboBox()
        field.addItem("0", 0)
        field.addItem("00", "00")
        for number in range(1, 100):
            field.addItem(str(number), number)
        return self._register("identity.jersey_number", field)  # type: ignore[return-value]

    def _vitals_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        identity = QGroupBox("Card Identity")
        form = QFormLayout(identity)
        form.addRow("Player name", self._line("identity.name"))
        form.addRow("Season / year", self._spin("identity.year", 1940, 2100, 2016))
        form.addRow("Import data from existing card", self._searchable_player_combo())
        form.addRow("Overall", self._spin("identity.overall", 25, 99, 75))
        form.addRow("Gem tier", self._combo("identity.tier", list(TIERS)))
        form.addRow("Theme", self._taxonomy_combo("identity.theme"))
        form.addRow("Collection", self._taxonomy_combo("identity.collection"))
        form.addRow("Franchise", self._combo("identity.franchise", list(NBA_FRANCHISES)))
        layout.addWidget(identity)

        player = QGroupBox("Player Vitals")
        grid = QGridLayout(player)
        grid.addWidget(QLabel("Primary position"), 0, 0)
        grid.addWidget(self._combo("identity.primary_position", list(POSITIONS)), 0, 1)
        grid.addWidget(QLabel("Secondary position"), 0, 2)
        grid.addWidget(self._combo("identity.secondary_position", list(POSITIONS), allow_blank=True), 0, 3)
        grid.addWidget(QLabel("Height (feet)"), 1, 0)
        grid.addWidget(self._spin("identity.height_feet", 4, 8, 6), 1, 1)
        grid.addWidget(QLabel("Height (inches)"), 1, 2)
        grid.addWidget(self._spin("identity.height_inches", 0, 11, 6), 1, 3)
        grid.addWidget(QLabel("Weight (lb)"), 2, 0)
        grid.addWidget(self._spin("identity.weight", 100, 400, 200), 2, 1)
        grid.addWidget(QLabel("Age"), 2, 2)
        grid.addWidget(self._spin("identity.age", 16, 65, 25), 2, 3)
        grid.addWidget(QLabel("From"), 3, 0)
        grid.addWidget(self._line("identity.from"), 3, 1)
        grid.addWidget(QLabel("Jersey number"), 3, 2)
        grid.addWidget(self._jersey_combo(), 3, 3)
        grid.addWidget(QLabel("Dominant hand"), 4, 0)
        grid.addWidget(self._combo("identity.dominant_hand", ["Left", "Right"]), 4, 1)
        grid.addWidget(QLabel("Dunk hand"), 4, 2)
        grid.addWidget(self._combo("identity.dominant_dunk_hand", ["Left", "Right", "Either"]), 4, 3)
        grid.addWidget(QLabel("Face ID"), 5, 0)
        grid.addWidget(self._spin("identity.face_id", 0, 65535, 0), 5, 1)
        grid.addWidget(QLabel("Portrait ID"), 5, 2)
        grid.addWidget(self._spin("identity.portrait_id", 0, 65535, 0), 5, 3)
        initiator = QCheckBox("Play Initiator")
        self._register("identity.play_initiator", initiator)
        grid.addWidget(initiator, 6, 0, 1, 2)
        layout.addWidget(player)

        editor = QGroupBox("In-Game Vitals and Play Types")
        editor_grid = QGridLayout(editor)
        editor_grid.addWidget(QLabel("Loyalty"), 0, 0)
        editor_grid.addWidget(self._spin("identity.loyalty", 0, 100, 100), 0, 1)
        editor_grid.addWidget(QLabel("Force non-starter"), 0, 2)
        editor_grid.addWidget(self._id_combo("identity.force_non_starter", FORCE_NON_STARTER_OPTIONS), 0, 3)
        editor_grid.addWidget(QLabel("Injury 1 type"), 1, 0)
        editor_grid.addWidget(self._id_combo("identity.injury_type_1", INJURY_OPTIONS), 1, 1)
        editor_grid.addWidget(QLabel("Injury 1 duration (days)"), 1, 2)
        editor_grid.addWidget(self._spin("identity.injury_duration_days_1", 0, 480, 0), 1, 3)
        editor_grid.addWidget(QLabel("Injury 2 type"), 2, 0)
        editor_grid.addWidget(self._id_combo("identity.injury_type_2", INJURY_OPTIONS), 2, 1)
        editor_grid.addWidget(QLabel("Injury 2 duration (days)"), 2, 2)
        editor_grid.addWidget(self._spin("identity.injury_duration_days_2", 0, 480, 0), 2, 3)
        for index in range(4):
            editor_grid.addWidget(QLabel(f"Play type {index + 1}"), 3 + index // 2, (index % 2) * 2)
            editor_grid.addWidget(
                self._id_combo(f"identity.play_type_{index + 1}", PLAY_TYPE_OPTIONS),
                3 + index // 2,
                (index % 2) * 2 + 1,
            )
        layout.addWidget(editor)
        layout.addStretch(1)
        return self._scroll(content)

    def set_preset_database(self, database: PlayerPresetDatabase) -> None:
        self._preset_database = database
        player = self._preset_combo
        if isinstance(player, QComboBox):
            typed_name = player.currentText()
            player.blockSignals(True)
            player.clear()
            for preset in database.presets:
                player.addItem(str(preset.get("label") or preset.get("name") or "Player"), preset)
            player.setEditText(typed_name)
            player.blockSignals(False)
            completer = QCompleter(player.model(), player)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            player.setCompleter(completer)
            completer.activated.connect(self._apply_completed_preset)
        theme = self._controls.get("identity.theme")
        if isinstance(theme, QComboBox):
            current = theme.currentText()
            self._replace_text_options(theme, database.themes, current)
            theme.currentTextChanged.connect(self._theme_changed)
        self._theme_changed(theme.currentText() if isinstance(theme, QComboBox) else "")

    @staticmethod
    def _replace_text_options(combo: QComboBox, values, current: str = "") -> None:
        combo.blockSignals(True)
        combo.clear()
        for value in values:
            combo.addItem(str(value), str(value))
        if current and combo.findText(current) < 0:
            combo.addItem(current, current)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _theme_changed(self, theme: str) -> None:
        collection = self._controls.get("identity.collection")
        if not isinstance(collection, QComboBox):
            return
        current = collection.currentText()
        mapping = self._preset_database.theme_collections or {}
        choices = mapping.get(theme) or self._preset_database.collections
        self._replace_text_options(collection, choices, current)

    @staticmethod
    def _merge_patch(target: dict, patch: dict) -> dict:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                PlayerDataEditor._merge_patch(target[key], value)
            else:
                target[key] = deepcopy(value)
        return target

    def _apply_selected_preset(self, index: int) -> None:
        player = self._preset_combo
        if not isinstance(player, QComboBox) or index < 0:
            return
        preset = player.itemData(index)
        patch = preset.get("patch") if isinstance(preset, dict) else None
        if not isinstance(patch, dict):
            return
        current = self.player_data()
        preserved_identity = {
            key: deepcopy(current["identity"].get(key))
            for key in (
                "name", "year", "overall", "tier", "theme", "collection",
                "franchise", "primary_position", "secondary_position",
            )
        }
        merged = self._merge_patch(current, patch)
        merged["identity"].update(preserved_identity)
        self.set_player_data(merged)

    def _apply_completed_preset(self, label: str) -> None:
        player = self._preset_combo
        if player is None:
            return
        index = player.findText(str(label), Qt.MatchFlag.MatchExactly)
        if index >= 0:
            player.setCurrentIndex(index)
            self._apply_selected_preset(index)

    def _ratings_page(self, groups, section: str, minimum: int, maximum: int, default: int) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        for group_name, fields in groups:
            box = QGroupBox(group_name)
            grid = QGridLayout(box)
            for index, field_name in enumerate(fields):
                row, column = divmod(index, 3)
                grid.addWidget(QLabel(pretty_name(field_name)), row, column * 2)
                grid.addWidget(self._spin(f"{section}.{field_name}", minimum, maximum, default), row, column * 2 + 1)
            layout.addWidget(box)
        layout.addStretch(1)
        return self._scroll(content)

    def _connect_overall_calculator(self) -> None:
        position = self._controls.get("identity.primary_position")
        if isinstance(position, QComboBox):
            position.currentIndexChanged.connect(self._update_overall_estimate)
        for key in ("identity.height_feet", "identity.height_inches"):
            control = self._controls.get(key)
            if isinstance(control, QSpinBox):
                control.valueChanged.connect(self._update_overall_estimate)
        durability_fields = tuple(
            field for field in self._overall_calculator._payload.get("durabilityFields", ())
        )
        for field in (*OVERALL_ATTRIBUTE_FIELDS, *durability_fields):
            control = self._controls.get(f"attributes.{field}")
            if isinstance(control, QSpinBox):
                control.valueChanged.connect(self._update_overall_estimate)

    def _current_overall_estimate(self) -> OverallEstimate:
        position = self._controls.get("identity.primary_position")
        if not isinstance(position, QComboBox):
            raise ValueError("Primary position control is unavailable")
        attributes = {}
        for field in OVERALL_ATTRIBUTE_FIELDS:
            control = self._controls.get(f"attributes.{field}")
            if not isinstance(control, QSpinBox):
                raise ValueError(f"Attribute control is unavailable: {field}")
            attributes[field] = control.value()
        durability = {}
        for field in self._overall_calculator._payload.get("durabilityFields", ()):
            control = self._controls.get(f"attributes.{field}")
            if not isinstance(control, QSpinBox):
                raise ValueError(f"Durability control is unavailable: {field}")
            durability[field] = control.value()
        feet = self._controls.get("identity.height_feet")
        inches = self._controls.get("identity.height_inches")
        if not isinstance(feet, QSpinBox) or not isinstance(inches, QSpinBox):
            raise ValueError("Height controls are unavailable")
        height_inches = feet.value() * 12 + inches.value()
        return self._overall_calculator.estimate(
            str(position.currentData() or ""), attributes,
            height_inches=height_inches, durability=durability,
        )

    def _update_overall_estimate(self, *_args) -> None:
        display = self._overall_live_display
        if display is None:
            return
        if not self._overall_calculator.available:
            display.setText("OVR unavailable")
            return
        try:
            estimate = self._current_overall_estimate()
        except ValueError as exc:
            display.setText("OVR unavailable")
            display.setToolTip(str(exc))
            return
        overall = self._controls.get("identity.overall")
        if isinstance(overall, QSpinBox):
            overall.setValue(estimate.overall)
        display.setText(f"{estimate.position} OVR {estimate.raw:.2f}")
        display.setToolTip(
            f"Rounds to {estimate.overall} OVR. Learned from {estimate.sample_count} official "
            f"{estimate.position} cards; held-out MAE ±{estimate.validation_mae:.2f}. "
            "Pink Diamonds and hidden cards are excluded."
        )

    def _signatures_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        info = QLabel("The readable label and verified byte ID are shown together. The byte ID is what the game receives.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #9fb0c5;")
        layout.addWidget(info)
        for group_name, fields in SIGNATURE_GROUPS:
            box = QGroupBox(group_name)
            form = QFormLayout(box)
            for field in fields:
                combo = self._id_combo(
                    f"signatures.{field['key']}",
                    field["options"],
                    dunk_labels=field["key"].startswith("dunk_package_"),
                )
                form.addRow(field["label"], combo)
            layout.addWidget(box)
        layout.addStretch(1)
        return self._scroll(content)

    def _badges_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        personality = QGroupBox("Personality Badges (blue, no tier)")
        grid = QGridLayout(personality)
        for index, badge in enumerate(PERSONALITY_BADGES):
            field = QCheckBox(pretty_name(badge))
            self._register(f"badges.personality.{badge}", field)
            row, column = divmod(index, 4)
            grid.addWidget(field, row, column)
        coach = QCheckBox("On-Court Coach")
        self._register("badges.on_court_coach", coach)
        grid.addWidget(coach, (len(PERSONALITY_BADGES) + 3) // 4, 0)
        layout.addWidget(personality)

        gameplay = QGroupBox("Gameplay Badges")
        game_grid = QGridLayout(gameplay)
        for index, badge in enumerate(GAMEPLAY_BADGES):
            game_grid.addWidget(QLabel(pretty_name(badge)), index // 3, (index % 3) * 2)
            combo = QComboBox()
            for value, label in enumerate(("None", "Bronze", "Silver", "Gold")):
                combo.addItem(label, value)
            self._register(f"badges.gameplay.{badge}", combo)
            game_grid.addWidget(combo, index // 3, (index % 3) * 2 + 1)
        layout.addWidget(gameplay)
        layout.addStretch(1)
        return self._scroll(content)

    def _hot_zones_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        box = QGroupBox("Court Zones")
        grid = QGridLayout(box)
        for index, field_name in enumerate(HOT_ZONES):
            grid.addWidget(QLabel(pretty_name(field_name)), index // 3, (index % 3) * 2)
            combo = QComboBox()
            combo.addItem("Cold", 0)
            combo.addItem("Neutral", 1)
            combo.addItem("Hot", 2)
            self._register(f"hot_zones.{field_name}", combo)
            grid.addWidget(combo, index // 3, (index % 3) * 2 + 1)
        layout.addWidget(box)
        layout.addStretch(1)
        return self._scroll(content)

    def set_player_data(self, value: dict | None) -> None:
        data = normalize_player_data(value)
        identity_data = data.get("identity") or {}
        self._source_identity = {
            "source_card_id": int(identity_data.get("source_card_id") or 0),
            "source_card_slug": str(identity_data.get("source_card_slug") or ""),
            "source_identity_ids": deepcopy(identity_data.get("source_identity_ids") or {}),
        }
        theme = self._controls.get("identity.theme")
        collection = self._controls.get("identity.collection")
        wanted_theme = str(data.get("identity", {}).get("theme") or "")
        wanted_collection = str(data.get("identity", {}).get("collection") or "")
        if isinstance(theme, QComboBox):
            if wanted_theme and theme.findText(wanted_theme) < 0:
                theme.addItem(wanted_theme, wanted_theme)
            theme.setCurrentIndex(max(0, theme.findText(wanted_theme)))
            self._theme_changed(wanted_theme)
        if isinstance(collection, QComboBox) and wanted_collection and collection.findText(wanted_collection) < 0:
            collection.addItem(wanted_collection, wanted_collection)
        for key, widget in self._controls.items():
            current = data
            for part in key.split("."):
                current = current.get(part) if isinstance(current, dict) else None
            widget.blockSignals(True)
            if isinstance(widget, QLineEdit):
                widget.setText(str(current or ""))
            elif isinstance(widget, QSpinBox):
                try:
                    widget.setValue(int(current))
                except (TypeError, ValueError):
                    pass
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(current))
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(current)) if key in {"identity.jersey_number", "identity.theme", "identity.collection"} else widget.findData(current)
                if index < 0:
                    index = widget.findText(str(current or ""))
                widget.setCurrentIndex(max(0, index))
            widget.blockSignals(False)
        self._update_overall_estimate()

    def player_data(self) -> dict:
        data = normalize_player_data(None)
        for key, widget in self._controls.items():
            if isinstance(widget, QLineEdit):
                value = widget.text().strip()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QComboBox):
                value = widget.currentData()
            else:
                continue
            target = data
            parts = key.split(".")
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
        data["identity"].update(self._source_identity)
        return data
