"""App.
"""

import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AzurePartsConfig(AppConfig):
    """App Config."""

    name = "vision_on_edge.azure_parts"

    def ready(self):
        """ready."""
        if "runserver" in sys.argv:
            # Import models in migrate/makemigration will occurs error.
            # pylint: disable = import-outside-toplevel
            # pylint: disable = unused-import

            from vision_on_edge.azure_parts import signals
            from vision_on_edge.azure_parts.models import Part
            from vision_on_edge.azure_projects.models import Project

            logger.info("Azure Part App Config ready while running server")

            create_demo = True
            if create_demo:
                logger.info("Creating demo parts...")

                # =============================================
                # Simple Part Detection                     ===
                # =============================================
                if (
                    Project.objects.filter(
                        is_demo=True, name="Demo Part Detection Project"
                    ).count()
                    != 1
                ):
                    return
                project_obj = Project.objects.get(
                    is_demo=True, name="Demo Part Detection Project"
                )
                for partname in [
                    "aeroplane",
                    "bicycle",
                    "bird",
                    "boat",
                    "bottle",
                    "bus",
                    "car",
                    "cat",
                    "chair",
                    "cow",
                    "diningtable",
                    "dog",
                    "horse",
                    "motorbike",
                    "person",
                    "pottedplant",
                    "sheep",
                    "sofa",
                    "train",
                    "tvmonitor",
                ]:
                    if not Part.objects.filter(
                        project=project_obj, name=partname
                    ).exists():
                        Part.objects.create(
                            project=project_obj, name=partname, description="Demo"
                        )
                # =============================================
                # Part Counting                             ===
                # =============================================
                try:
                    project_obj = Project.objects.get(
                        is_demo=True, name="Demo Part Counting Project"
                    )
                    for partname in ["Box"]:
                        Part.objects.update_or_create(
                            project=project_obj,
                            name=partname,
                            defaults={"description": "Demo"},
                        )
                except Exception:
                    logger.error("Create Demo Part Counting Parts error")
                # =============================================
                # Employee safety                           ===
                # =============================================
                try:
                    project_obj = Project.objects.get(
                        is_demo=True, name="Demo Employee Safety Project"
                    )
                    for partname in ["Person"]:
                        Part.objects.update_or_create(
                            project=project_obj,
                            name=partname,
                            defaults={"description": "Demo"},
                        )
                except Exception:
                    logger.error("Create Demo Employee Safety Parts error")
                # =============================================
                # Defect Detection                          ===
                # =============================================
                try:
                    project_obj = Project.objects.get(
                        is_demo=True, name="Demo Defect Detection Project"
                    )
                    for partname in ["Bottle - OK", "Bottle - NG"]:
                        Part.objects.update_or_create(
                            project=project_obj,
                            name=partname,
                            defaults={"description": "Demo"},
                        )
                except Exception:
                    logger.error("Create Demo Defect Defection Parts error")
            logger.info("Part App Config end while running server")
