import type { StrategyParameterDefinition } from "../api/types";

interface StrategyParameterFieldsProps {
  definitions: StrategyParameterDefinition[];
  namePrefix?: string;
}

export function StrategyParameterFields({
  definitions,
  namePrefix = "parameter",
}: StrategyParameterFieldsProps) {
  if (definitions.length === 0) return null;

  return (
    <section className="parameter-sheet" aria-labelledby={`${namePrefix}-parameter-title`}>
      <div className="parameter-sheet-heading">
        <div>
          <span className="section-code">PARAMETERS</span>
          <h3 id={`${namePrefix}-parameter-title`}>策略参数</h3>
        </div>
        <span>{definitions.length} 项</span>
      </div>
      <div className="parameter-field-grid">
        {definitions.map((definition) => (
          <ParameterField
            key={definition.name}
            definition={definition}
            inputName={`${namePrefix}:${definition.name}`}
          />
        ))}
      </div>
    </section>
  );
}

interface ParameterFieldProps {
  definition: StrategyParameterDefinition;
  inputName: string;
}

function ParameterField({ definition, inputName }: ParameterFieldProps) {
  if (definition.type === "bool") {
    return (
      <label className="parameter-check">
        <input type="checkbox" name={inputName} defaultChecked={definition.default === true} />
        <span>
          <strong>{definition.label}</strong>
          {definition.description ? <small>{definition.description}</small> : null}
        </span>
      </label>
    );
  }

  return (
    <label className="field parameter-field">
      <span>{definition.label}</span>
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
      {definition.description ? <small>{definition.description}</small> : null}
    </label>
  );
}
