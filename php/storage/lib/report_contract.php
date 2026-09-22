<?php

declare(strict_types=1);

const LMTS_REPORT_CONTRACT_FILE = 'LMTS_Benchmark_Report_Template_v1.1.schema.json';

function lmts_contract_error(string $path, string $message): never {
    throw new InvalidArgumentException($path . ': ' . $message);
}

function lmts_schema_error(string $path, string $message): never {
    throw new LogicException($path . ': ' . $message);
}

function lmts_schema_keywords(): array {
    return [
        '$schema' => true,
        '$id' => true,
        '$defs' => true,
        '$ref' => true,
        'title' => true,
        'description' => true,
        'type' => true,
        'required' => true,
        'properties' => true,
        'additionalProperties' => true,
        'minProperties' => true,
        'items' => true,
        'minLength' => true,
        'minimum' => true,
        'uniqueItems' => true,
        'format' => true,
        'const' => true,
        'anyOf' => true,
        'x-lmts-contract' => true,
    ];
}

function lmts_assert_supported_schema(stdClass $schema, string $path = '$schema'): void {
    $supported = lmts_schema_keywords();
    foreach (get_object_vars($schema) as $keyword => $value) {
        if (!isset($supported[$keyword])) {
            lmts_schema_error($path, "unsupported JSON Schema keyword '$keyword'");
        }
    }

    if (isset($schema->{'$defs'})) {
        if (!($schema->{'$defs'} instanceof stdClass)) lmts_schema_error($path . '.$defs', 'must be an object');
        foreach (get_object_vars($schema->{'$defs'}) as $name => $child) {
            if (!($child instanceof stdClass)) lmts_schema_error($path . '.$defs.' . $name, 'must be a schema object');
            lmts_assert_supported_schema($child, $path . '.$defs.' . $name);
        }
    }
    if (isset($schema->properties)) {
        if (!($schema->properties instanceof stdClass)) lmts_schema_error($path . '.properties', 'must be an object');
        foreach (get_object_vars($schema->properties) as $name => $child) {
            if (!($child instanceof stdClass)) lmts_schema_error($path . '.properties.' . $name, 'must be a schema object');
            lmts_assert_supported_schema($child, $path . '.properties.' . $name);
        }
    }
    if (isset($schema->additionalProperties) && $schema->additionalProperties instanceof stdClass) {
        lmts_assert_supported_schema($schema->additionalProperties, $path . '.additionalProperties');
    }
    if (isset($schema->items)) {
        if (!($schema->items instanceof stdClass)) lmts_schema_error($path . '.items', 'must be a schema object');
        lmts_assert_supported_schema($schema->items, $path . '.items');
    }
    if (isset($schema->anyOf)) {
        if (!is_array($schema->anyOf)) lmts_schema_error($path . '.anyOf', 'must be an array');
        foreach ($schema->anyOf as $index => $child) {
            if (!($child instanceof stdClass)) lmts_schema_error($path . ".anyOf[$index]", 'must be a schema object');
            lmts_assert_supported_schema($child, $path . ".anyOf[$index]");
        }
    }
}

function lmts_load_report_contract(string $path): stdClass {
    $raw = file_get_contents($path);
    if ($raw === false) throw new RuntimeException('cannot read benchmark report contract');
    $schema = json_decode($raw, false, 512, JSON_THROW_ON_ERROR);
    if (!($schema instanceof stdClass)) throw new RuntimeException('benchmark report contract root must be an object');
    lmts_assert_supported_schema($schema);
    return $schema;
}

function lmts_pointer_token(string $token): string {
    return str_replace(['~1', '~0'], ['/', '~'], $token);
}

function lmts_resolve_local_ref(stdClass $root, string $ref): stdClass {
    if (!str_starts_with($ref, '#/')) lmts_schema_error('$schema', "only local JSON Schema refs are supported: $ref");
    $node = $root;
    foreach (explode('/', substr($ref, 2)) as $rawToken) {
        $token = lmts_pointer_token($rawToken);
        if (!($node instanceof stdClass) || !property_exists($node, $token)) {
            lmts_schema_error('$schema', "unresolved JSON Schema ref: $ref");
        }
        $node = $node->{$token};
    }
    if (!($node instanceof stdClass)) lmts_schema_error('$schema', "JSON Schema ref does not resolve to a schema object: $ref");
    return $node;
}

function lmts_value_fingerprint(mixed $value): string {
    if ($value instanceof stdClass) {
        $properties = get_object_vars($value);
        ksort($properties, SORT_STRING);
        $parts = [];
        foreach ($properties as $key => $item) {
            $parts[] = json_encode((string)$key, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR)
                . ':' . lmts_value_fingerprint($item);
        }
        return 'o{' . implode(',', $parts) . '}';
    }
    if (is_array($value)) {
        return 'a[' . implode(',', array_map('lmts_value_fingerprint', $value)) . ']';
    }
    return 's:' . json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
}

function lmts_type_matches(mixed $value, string $type): bool {
    return match ($type) {
        'object' => $value instanceof stdClass,
        'array' => is_array($value),
        'string' => is_string($value),
        'number' => is_int($value) || is_float($value),
        'integer' => is_int($value),
        'boolean' => is_bool($value),
        'null' => $value === null,
        default => throw new LogicException("unsupported JSON Schema type '$type'"),
    };
}

function lmts_validate_datetime(string $value, string $path): void {
    if (!preg_match('/^\d{4}-\d{2}-\d{2}T/', $value)) lmts_contract_error($path, 'must be an RFC 3339 date-time');
    try {
        new DateTimeImmutable($value);
    } catch (Throwable $error) {
        lmts_contract_error($path, 'must be a valid date-time');
    }
}

function lmts_validate_schema_value(mixed $value, stdClass $schema, stdClass $root, string $path): void {
    if (isset($schema->{'$ref'})) {
        if (!is_string($schema->{'$ref'})) lmts_schema_error($path, '$ref must be a string');
        lmts_validate_schema_value($value, lmts_resolve_local_ref($root, $schema->{'$ref'}), $root, $path);
    }

    if (isset($schema->anyOf)) {
        $matched = false;
        foreach ($schema->anyOf as $candidate) {
            try {
                lmts_validate_schema_value($value, $candidate, $root, $path);
                $matched = true;
                break;
            } catch (InvalidArgumentException $error) {
                // Try the next explicitly declared schema branch.
            }
        }
        if (!$matched) lmts_contract_error($path, 'does not match any allowed schema');
    }

    if (property_exists($schema, 'const')) {
        if (lmts_value_fingerprint($value) !== lmts_value_fingerprint($schema->const)) {
            lmts_contract_error($path, 'does not match the required constant value');
        }
    }

    if (isset($schema->type)) {
        if (!is_string($schema->type)) lmts_schema_error($path, 'schema type must be a string');
        if (!lmts_type_matches($value, $schema->type)) lmts_contract_error($path, 'must be of type ' . $schema->type);
    }

    if (is_string($value)) {
        if (isset($schema->minLength) && strlen($value) < (int)$schema->minLength) {
            lmts_contract_error($path, 'is shorter than minLength');
        }
        if (($schema->format ?? null) === 'date-time') lmts_validate_datetime($value, $path);
    }

    if ((is_int($value) || is_float($value)) && isset($schema->minimum) && $value < $schema->minimum) {
        lmts_contract_error($path, 'is below minimum');
    }

    if ($value instanceof stdClass) {
        $properties = get_object_vars($value);
        if (isset($schema->minProperties) && count($properties) < (int)$schema->minProperties) {
            lmts_contract_error($path, 'has fewer properties than minProperties');
        }
        if (isset($schema->required)) {
            if (!is_array($schema->required)) lmts_schema_error($path, 'required must be an array');
            foreach ($schema->required as $required) {
                if (!is_string($required)) lmts_schema_error($path, 'required names must be strings');
                if (!property_exists($value, $required)) lmts_contract_error($path, "missing required property '$required'");
            }
        }
        $declared = [];
        if (isset($schema->properties)) {
            foreach (get_object_vars($schema->properties) as $name => $childSchema) {
                $declared[$name] = true;
                if (property_exists($value, $name)) {
                    lmts_validate_schema_value($value->{$name}, $childSchema, $root, $path . '.' . $name);
                }
            }
        }
        foreach ($properties as $name => $item) {
            if (isset($declared[$name])) continue;
            if (!property_exists($schema, 'additionalProperties') || $schema->additionalProperties === true) continue;
            if ($schema->additionalProperties === false) lmts_contract_error($path . '.' . $name, 'additional property is not allowed');
            if ($schema->additionalProperties instanceof stdClass) {
                lmts_validate_schema_value($item, $schema->additionalProperties, $root, $path . '.' . $name);
                continue;
            }
            lmts_schema_error($path, 'additionalProperties must be boolean or schema object');
        }
    }

    if (is_array($value)) {
        if (isset($schema->items)) {
            foreach ($value as $index => $item) {
                lmts_validate_schema_value($item, $schema->items, $root, $path . '[' . $index . ']');
            }
        }
        if (($schema->uniqueItems ?? false) === true) {
            $seen = [];
            foreach ($value as $index => $item) {
                $fingerprint = lmts_value_fingerprint($item);
                if (isset($seen[$fingerprint])) lmts_contract_error($path . '[' . $index . ']', 'duplicates an earlier array item');
                $seen[$fingerprint] = true;
            }
        }
    }
}

function lmts_validate_report_semantics(stdClass $report): void {
    $dimensions = get_object_vars($report->dimensions);
    $entityGroups = get_object_vars($report->entities);
    $metricDefinitions = get_object_vars($report->metric_definitions);

    foreach ($dimensions as $dimensionId => $dimension) {
        $entityType = $dimension->entity_type;
        if (!isset($entityGroups[$entityType]) || !($entityGroups[$entityType] instanceof stdClass)) {
            lmts_contract_error('$.dimensions.' . $dimensionId, "references missing entity type '$entityType'");
        }
    }

    $recordIds = [];
    $computedOutcomes = [];
    foreach ($report->records as $index => $record) {
        $path = '$.records[' . $index . ']';
        if (isset($recordIds[$record->id])) lmts_contract_error($path . '.id', 'duplicate record id');
        $recordIds[$record->id] = true;

        foreach (get_object_vars($record->coordinates) as $dimensionId => $entityId) {
            if (!isset($dimensions[$dimensionId])) lmts_contract_error($path . '.coordinates.' . $dimensionId, 'references an unknown dimension');
            $entityType = $dimensions[$dimensionId]->entity_type;
            $group = $entityGroups[$entityType];
            if (!property_exists($group, $entityId)) {
                lmts_contract_error($path . '.coordinates.' . $dimensionId, "references missing entity '$entityId'");
            }
        }

        foreach (get_object_vars($record->metrics) as $metricName => $metric) {
            if (!isset($metricDefinitions[$metricName])) {
                lmts_contract_error($path . '.metrics.' . $metricName, 'has no metric definition');
            }
            $definition = $metricDefinitions[$metricName];
            if (isset($metric->unit) && isset($definition->unit) && $metric->unit !== $definition->unit) {
                lmts_contract_error($path . '.metrics.' . $metricName . '.unit', 'does not match metric definition unit');
            }
        }

        $result = $record->outcome->result;
        $computedOutcomes[$result] = ($computedOutcomes[$result] ?? 0) + 1;
    }

    if ($report->summary->records !== count($report->records)) {
        lmts_contract_error('$.summary.records', 'does not match records array length');
    }
    foreach (get_object_vars($report->summary->outcomes) as $result => $count) {
        $expected = $computedOutcomes[$result] ?? 0;
        if ($count !== $expected) lmts_contract_error('$.summary.outcomes.' . $result, "expected $expected from records");
        unset($computedOutcomes[$result]);
    }
    if ($computedOutcomes !== []) {
        $missing = array_key_first($computedOutcomes);
        lmts_contract_error('$.summary.outcomes', "missing outcome counter '$missing'");
    }

    foreach ($report->views as $index => $view) {
        if ($view->type !== 'matrix') continue;
        foreach (['row_dimension', 'column_dimension', 'value'] as $field) {
            if (!isset($view->{$field}) || !is_string($view->{$field}) || trim($view->{$field}) === '') {
                lmts_contract_error('$.views[' . $index . '].' . $field, 'is required for matrix views');
            }
        }
        if (!isset($dimensions[$view->row_dimension])) lmts_contract_error('$.views[' . $index . '].row_dimension', 'references an unknown dimension');
        if (!isset($dimensions[$view->column_dimension])) lmts_contract_error('$.views[' . $index . '].column_dimension', 'references an unknown dimension');
    }

    if (isset($dimensions['target']) && isset($report->summary->targets)) {
        $entityType = $dimensions['target']->entity_type;
        $expected = count(get_object_vars($entityGroups[$entityType]));
        if ($report->summary->targets !== $expected) lmts_contract_error('$.summary.targets', "expected $expected target entities");
    }
    if (isset($dimensions['test']) && isset($report->summary->tests)) {
        $entityType = $dimensions['test']->entity_type;
        $expected = count(get_object_vars($entityGroups[$entityType]));
        if ($report->summary->tests !== $expected) lmts_contract_error('$.summary.tests', "expected $expected test entities");
    }

    if (isset($report->report->benchmark) && $report->report->benchmark instanceof stdClass) {
        $benchmark = $report->report->benchmark;
        if (isset($benchmark->target_ids) && is_array($benchmark->target_ids) && isset($dimensions['target'])) {
            $group = $entityGroups[$dimensions['target']->entity_type];
            foreach ($benchmark->target_ids as $index => $targetId) {
                if (!is_string($targetId) || !property_exists($group, $targetId)) {
                    lmts_contract_error('$.report.benchmark.target_ids[' . $index . ']', 'references a missing target entity');
                }
            }
        }
        if (isset($benchmark->test_refs) && is_array($benchmark->test_refs) && isset($dimensions['test'])) {
            $group = $entityGroups[$dimensions['test']->entity_type];
            foreach ($benchmark->test_refs as $index => $testRef) {
                if (!is_string($testRef) || !property_exists($group, $testRef)) {
                    lmts_contract_error('$.report.benchmark.test_refs[' . $index . ']', 'references a missing test entity');
                }
            }
        }
    }
}

function lmts_validate_report_document(stdClass $document, string $contractPath): void {
    $schema = lmts_load_report_contract($contractPath);
    lmts_validate_schema_value($document, $schema, $schema, '$');
    lmts_validate_report_semantics($document);
}
