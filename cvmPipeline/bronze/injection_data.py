from pyspark import pipelines as dp

@dp.table()
def raw_cvm_data():
    return (
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "csv")
            .option("sep", ";")
            .option("header", "true")
            .option("encoding", "ISO-8859-1")
            .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
            .load("/Volumes/workspace/bronze/s3_cvm_volume")
        )