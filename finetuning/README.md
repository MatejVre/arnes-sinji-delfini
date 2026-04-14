# Fine-tuning slovenskega javnoupravnega asistenta

Ta del repozitorija vsebuje **fine-tuning del** širšega projekta lokalnega asistenta za slovensko javno upravo.

Glavni cilj ni memoriranje zakonodaje, temveč prilagoditev modela, da:

- bolje razume terminologijo slovenske javne uprave,
- bolje povzema uradna in postopkovna besedila,
- zna izluščiti strukturirane podatke,
- bolje razvršča dokumente po resorju/področju/tipu,
- odgovarja v jasnem in formalnem administrativnem slogu,
- pravilno zavrne ali usmeri odgovor, kadar to zahteva vhodni signal politike.

## Osnovni model in pristop

- Osnovni model: `cjvt/GaMS3-12B-Instruct`
- Glavna metoda fine-tuninga: `QLoRA`
- Primerjalna metoda: `LoRA`

## Kratek pregled procesa

Celoten potek je naslednji:

1. Zbiranje podatkov iz uradnih slovenskih javnosektorskih virov.
2. Čiščenje in normalizacija dokumentov v enotno JSONL obliko.
3. Razrez dokumentov na odseke/chunke.
4. Gradnja učnih primerov za več nalog:
   - klasifikacija,
   - povzemanje,
   - ekstrakcija,
   - grounded QA,
   - zavrnitev/usmerjanje.
5. Fine-tuning modela z uporabo PEFT pristopov (`QLoRA`, `LoRA`).
6. Primerjava modelov na zadržanih evalvacijskih nizih.

## Viri podatkov

Uporabljeni so bili predvsem uradni slovenski viri:

- `GOV.SI`
- `eUprava`
- `SPOT`
- `e-JN`
- izbrani referenčni deli `OPSI` in `PISRS`

Podatki so bili pridobljeni s kombinacijo:

- ciljanega zajema spletnih vsebin,
- ročnega zbiranja pomembnih dokumentov,
- source-grounded sintetičnega dopolnjevanja za slabše zastopane naloge.

## Naloge, na katerih se model uči

Repozitorij pokriva naslednje naloge:

- **klasifikacija**: napoved oznak, kot so ministrstvo, področje in tip dokumenta,
- **povzemanje**: kratek in zvest povzetek uradnega besedila,
- **ekstrakcija**: izluščenje strukturiranih podatkov iz besedila,
- **grounded QA**: odgovor samo na podlagi priloženega konteksta,
- **zavrnitev/usmerjanje**: pravilen odziv, kadar za odgovor ni dovolj podlage ali je potrebna usmeritev.

## Struktura

### `configs/`

Konfiguracije za pripravo podatkov, učenje in primerjavo modelov.

Pomembne datoteke:

- `qlora_gams3_12b_instruct_reviewed_fp16_v100.yaml`  
  Glavna QLoRA konfiguracija za V100/V100S.
- `lora_gams3_12b_instruct_reviewed_h100.yaml`  
  LoRA konfiguracija za H100.
- `model_comparison_reviewed.yaml`  
  Konfiguracija za primerjavo baseline/QLoRA/LoRA.

### `data/`

Glavna podatkovna mapa projekta.

Pomembne podmape:

- `cleaned/`  
  Očiščen korpus dokumentov.
- `chunks/`  
  Normalizirani dokumenti in razrezani odseki.
- `sft/`  
  Učni nizi za supervised fine-tuning.
- `eval/`  
  Zadržani evalvacijski primeri.
- `manifests/`  
  Povzetki, inventarji, delitve na train/val/test.
- `reviews/`  
  Delovne datoteke za pregled in promocijo primerov.

### `scripts/`

Python skripte za pripravo podatkov, učenje, evalvacijo in izvoz modelov.

Najpomembnejše:

- `train_qlora.py`  
  Fine-tuning z QLoRA.
- `train_lora.py`  
  Fine-tuning z LoRA.
- `evaluate_models.py`  
  Primerjava baseline, QLoRA in LoRA modelov.
- `merge_adapter.py`  
  Združevanje adapterja z osnovnim modelom v enoten export.

### `slurm/`

Batch skripte za zagon na gruči Arnes SLING.

Najpomembnejše:

- `train_qlora_reviewed_sling.sbatch`
- `train_lora_reviewed_sling.sbatch`
- `evaluate_models_sling.sbatch`
- `evaluate_models_synthetic_sling.sbatch`
- `merge_adapter_sling.sbatch`

### `runs/`

Rezultati dejanskih zagonov:

- adapterji po fine-tuningu,
- checkpointi,
- primerjave modelov,
- evalvacijski izhodi.

## Kaj pomeni rezultat fine-tuninga

Fine-tuning v tem repozitoriju ne ustvari  novega samostojnega modela, ampak predvsem **adapter**.

Ključni datoteki za uporabo adapterja sta:

- `adapter_model.safetensors`
- `adapter_config.json`

Po potrebi se adapter lahko z `merge_adapter.py` združi z osnovnim modelom v enoten model za streženje.