import type { StrategyParameterDefinition } from "../api/types";
import { useI18n } from "../i18n/I18nContext";
import { localizeParameter } from "../lib/parameterLocalization";

interface StrategyParameterFieldsProps {
  definitions: StrategyParameterDefinition[];
  namePrefix?: string;
}

export function StrategyParameterFields({
  definitions,
  namePrefix = "parameter",
}: StrategyParameterFieldsProps) {
  const { locale, t } = useI18n();
  if (definitions.length === 0) return null;

  return (
    <section className="parameter-sheet" aria-labelledby={`${namePrefix}-parameter-title`}>
      <div className="parameter-sheet-heading">
        <div>
          <span className="section-code">PARAMETERS</span>
          <h3 id={`${namePrefix}-parameter-title`}>{t("parameters.title")}</h3>
        </div>
        <span>{t("parameters.count", { count: definitions.length })}</span>
      </div>
      <div className="parameter-field-grid">
        {definitions.map((definition) => (
          <ParameterField
            key={definition.name}
            definition={definition}
            inputName={`${namePrefix}:${definition.name}`}
            locale={locale}
          />
        ))}
      </div>
    </section>
  );
}

interface ParameterFieldProps {
  definition: StrategyParameterDefinition;
  inputName: string;
  locale: "zh-CN" | "en-US";
}

function ParameterField({ definition, inputName, locale }: ParameterFieldProps) {
  const copy = localizeParameter(definition, locale);
  if (definition.type === "bool") {
    return (
      <label className="parameter-check">
        <input type="checkbox" name={inputName} defaultChecked={definition.default === true} />
        <span>
          <strong>{copy.label}</strong>
          {copy.description ? <small>{copy.description}</small> : null}
        </span>
      </label>
    );
  }

  return (
    <label className="field parameter-field">
      <span>{copy.label}</span>
      {definition.choices ? (
        <select name={inputName} defaultValue={String(definition.default)}>
          {definition.choices.map((choice) => (
            <option key={String(choice)} value={String(choice)}>{String(choice)}</option>
          ))}
        </select>
      ) : (
        <input
          type={definition.type === "string" ? "text" : "number"}
          name={inputName}
          defaultValue={String(definition.default)}
          min={definition.min}
          max={definition.max}
          step={definition.step ?? (definition.type === "int" ? 1 : "any")}
          required
        />
      )}
      {copy.description ? <small>{copy.description}</small> : null}
    </label>
  );
}
