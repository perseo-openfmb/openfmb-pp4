import asyncio, hashlib, nats, logging, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pb2"))
import switchmodule_pb2
import resourcemodule_pb2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GK] %(message)s")
log = logging.getLogger(__name__)

NATS_URL   = os.getenv("NATS_URL", "nats://nats:4222")
VALUE_LIMIT = 1000.0

SOURCE_MRID_SWITCH = "00000002-0003-1001-0000-000000000000"
TARGET_MRID_SWITCH = "00000002-0003-1001-0000-100000000000"

SOURCE_MRID_RESOURCE = "00000006-0100-0001-0000-000000002700"
TARGET_MRID_RESOURCE = "00000006-0100-1001-0000-000000002700"


SUBJECTS = [
    f"openfmb.switchmodule.SwitchDiscreteControlProfile.{SOURCE_MRID_SWITCH}",
    f"openfmb.resourcemodule.ResourceDiscreteControlProfile.{SOURCE_MRID_RESOURCE}",
]

_published = set()

def _already_published(data: bytes) -> bool:
    h = hashlib.md5(data).hexdigest()
    if h in _published:
        return True
    _published.add(h)
    if len(_published) > 1000:
        _published.clear()
    return False


async def main():
    nc = await nats.connect(NATS_URL, max_reconnect_attempts=-1, reconnect_time_wait=3)
    log.info(f"Conectado a {NATS_URL}")

    async def handler(msg):
        if _already_published(msg.data):
            return

        parts = msg.subject.split(".")
        profile_key = f"{parts[1]}.{parts[2]}"
        subject_mrid = parts[3]

        if profile_key == "switchmodule.SwitchDiscreteControlProfile":
            profile = switchmodule_pb2.SwitchDiscreteControlProfile()
            profile.ParseFromString(msg.data)
            inner_mrid = profile.protectedSwitch.conductingEquipment.mRID
            log.info(
                f"CAPTURADO  → {msg.subject}\n"
                f"  Perfil: {profile_key}\n"
                f"  mRID (payload): {inner_mrid}"
            )
            if inner_mrid == SOURCE_MRID_SWITCH:
                profile.protectedSwitch.conductingEquipment.mRID = TARGET_MRID_SWITCH
                new_data = profile.SerializeToString()
                new_subject = msg.subject.replace(SOURCE_MRID_SWITCH, TARGET_MRID_SWITCH)
                await nc.publish(new_subject, new_data)
                log.info(f"RE-PUBLICADO → {new_subject} ({len(new_data)} bytes)")

        elif profile_key == "resourcemodule.ResourceDiscreteControlProfile":
            profile = resourcemodule_pb2.ResourceDiscreteControlProfile()
            profile.ParseFromString(msg.data)
            inner_mrid = profile.conductingEquipment.mRID
            ggio_list = profile.resourceDiscreteControl.analogControlGGIO

            if not ggio_list:
                log.info(f"CAPTURADO  → {msg.subject} (sin analogControlGGIO)")
                return

            if inner_mrid == SOURCE_MRID_RESOURCE:

                ctl_val = ggio_list[0].AnOut.ctlVal
                log.info(
                    f"CAPTURADO  → {msg.subject}\n"
                    f"  Perfil: {profile_key}\n"
                    f"  mRID (payload): {inner_mrid}\n"
                    f"  analogControlGGIO[0].AnOut.ctlVal: {ctl_val}"
                )

                if ctl_val > VALUE_LIMIT:
                    log.info(f"BLOQUEADO: {ctl_val} > {VALUE_LIMIT}")
                    return

                log.info(f"RERMITIDO: {ctl_val} <= {VALUE_LIMIT}")
                profile.conductingEquipment.mRID = TARGET_MRID_RESOURCE
                new_data = profile.SerializeToString()
                await nc.publish(msg.subject, new_data)
                log.info(f"RE-PUBLICADO → {msg.subject} ({len(new_data)} bytes)")

    for sub in SUBJECTS:
        await nc.subscribe(sub, cb=handler)
        log.info(f"Escuchando: {sub}")

    await asyncio.Future()


asyncio.run(main())
